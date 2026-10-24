from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes import chat as chat_routes
from app.core.security import create_access_token, get_password_hash
from app.models.chat import ChatMessage, ChatSession, MessageRole
from app.models.document import Document, DocumentStatus
from app.models.user import User, UserRole


def _create_user(db: Session, email: str, role: UserRole = UserRole.USER) -> User:
    user = User(
        full_name=email.split("@")[0],
        email=email,
        password_hash=get_password_hash("test-password"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(subject=user.id, role=user.role.value)
    return {"Authorization": f"Bearer {token}"}


def _create_document(
    db: Session,
    uploader: User,
    *,
    title: str,
    is_public: bool,
) -> Document:
    document = Document(
        title=title,
        filename=f"{title}.pdf",
        file_path=f"{title}.pdf",
        uploader_id=uploader.id,
        is_public=is_public,
        chroma_collection="pending",
        chunk_count=1,
        page_count=1,
        file_hash=f"{len(title):064d}",
        status=DocumentStatus.READY,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def test_create_session_supports_all_accessible_or_selected_document(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _create_user(db_session, "chat-scope-admin@example.com", UserRole.ADMIN)
    user = _create_user(db_session, "chat-scope-user@example.com")
    public_doc = _create_document(
        db_session,
        admin,
        title="Public Guide",
        is_public=True,
    )
    private_doc = _create_document(
        db_session,
        admin,
        title="Private Guide",
        is_public=False,
    )

    all_docs = client.post("/api/chat/sessions", headers=_headers(user), json={})
    assert all_docs.status_code == 201
    assert all_docs.json()["document_id"] is None
    assert all_docs.json()["document_title"] is None

    selected = client.post(
        "/api/chat/sessions",
        headers=_headers(user),
        json={"document_id": public_doc.id},
    )
    assert selected.status_code == 201
    assert selected.json()["document_title"] == "Public Guide"

    private_for_user = client.post(
        "/api/chat/sessions",
        headers=_headers(user),
        json={"document_id": private_doc.id},
    )
    assert private_for_user.status_code == 404

    private_for_admin = client.post(
        "/api/chat/sessions",
        headers=_headers(admin),
        json={"document_id": private_doc.id},
    )
    assert private_for_admin.status_code == 201
    assert private_for_admin.json()["document_title"] == "Private Guide"


def test_send_message_persists_exchange_sources_and_first_message_title(
    client: TestClient,
    db_session: Session,
    monkeypatch: Any,
) -> None:
    user = _create_user(db_session, "chat-message-user@example.com")
    document = _create_document(
        db_session,
        user,
        title="Accessible",
        is_public=True,
    )
    session = ChatSession(user_id=user.id, document_id=document.id)
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    calls: list[dict[str, Any]] = []

    def fake_answer(**kwargs: Any):
        calls.append(kwargs)
        return (
            "The answer is grounded [S1].",
            [
                {
                    "source_label": "[S1]",
                    "document_id": document.id,
                    "document_title": document.title,
                    "page": 2,
                    "chunk_id": "doc_chunk_1",
                    "snippet": "Evidence",
                }
            ],
        )

    monkeypatch.setattr(chat_routes, "answer_rag_query", fake_answer)
    response = client.post(
        f"/api/chat/sessions/{session.id}/messages",
        headers=_headers(user),
        json={"content": "  What is the answer?  "},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_message"]["content"] == "What is the answer?"
    assert body["user_message"]["role"] == "user"
    assert body["assistant_message"]["role"] == "assistant"
    assert body["assistant_message"]["sources"][0]["page"] == 2
    assert calls[0]["target_document_id"] == document.id
    assert db_session.query(ChatMessage).filter_by(session_id=session.id).count() == 2
    db_session.refresh(session)
    assert session.title == "What is the answer?"


def test_message_uses_current_access_scope_when_bound_document_was_deleted(
    client: TestClient,
    db_session: Session,
    monkeypatch: Any,
) -> None:
    user = _create_user(db_session, "chat-deleted-doc-user@example.com")
    admin = _create_user(db_session, "chat-deleted-doc-admin@example.com", UserRole.ADMIN)
    document = _create_document(
        db_session,
        admin,
        title="Deleted Later",
        is_public=True,
    )
    session = ChatSession(user_id=user.id, document_id=document.id)
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    db_session.delete(document)
    db_session.commit()
    db_session.refresh(session)
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        chat_routes,
        "answer_rag_query",
        lambda **kwargs: (
            calls.append(kwargs) or "No evidence found.",
            [],
        ),
    )

    response = client.post(
        f"/api/chat/sessions/{session.id}/messages",
        headers=_headers(user),
        json={"content": "Ask after document deletion"},
    )

    assert response.status_code == 200
    assert calls[0]["target_document_id"] is None


def test_private_document_visibility_change_hides_bound_session_and_messages(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _create_user(db_session, "chat-private-admin@example.com", UserRole.ADMIN)
    user = _create_user(db_session, "chat-private-user@example.com")
    document = _create_document(
        db_session,
        admin,
        title="Changed to Private",
        is_public=True,
    )
    session = ChatSession(user_id=user.id, document_id=document.id)
    db_session.add(session)
    db_session.commit()
    document.is_public = False
    db_session.commit()

    detail = client.get(
        f"/api/chat/sessions/{session.id}",
        headers=_headers(user),
    )
    send = client.post(
        f"/api/chat/sessions/{session.id}/messages",
        headers=_headers(user),
        json={"content": "Try to query private document"},
    )
    listed = client.get("/api/chat/sessions", headers=_headers(user))

    assert detail.status_code == 404
    assert send.status_code == 404
    assert listed.status_code == 200
    assert listed.json()[0]["document_title"] is None


def test_chat_session_ownership_isolation_for_read_message_and_delete(
    client: TestClient,
    db_session: Session,
    monkeypatch: Any,
) -> None:
    owner = _create_user(db_session, "chat-owner@example.com")
    other = _create_user(db_session, "chat-other@example.com")
    session = ChatSession(user_id=owner.id, title="Owner session")
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    monkeypatch.setattr(
        chat_routes,
        "answer_rag_query",
        lambda **kwargs: ("Should not run", []),
    )

    detail = client.get(
        f"/api/chat/sessions/{session.id}",
        headers=_headers(other),
    )
    send = client.post(
        f"/api/chat/sessions/{session.id}/messages",
        headers=_headers(other),
        json={"content": "Unauthorized query"},
    )
    delete = client.delete(
        f"/api/chat/sessions/{session.id}",
        headers=_headers(other),
    )

    assert detail.status_code == send.status_code == delete.status_code == 404
    assert db_session.get(ChatSession, session.id) is not None


def test_chat_message_failure_is_not_persisted_and_empty_content_is_rejected(
    client: TestClient,
    db_session: Session,
    monkeypatch: Any,
) -> None:
    user = _create_user(db_session, "chat-failure-user@example.com")
    session = ChatSession(user_id=user.id)
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    monkeypatch.setattr(
        chat_routes,
        "answer_rag_query",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("private backend detail")),
    )

    blank = client.post(
        f"/api/chat/sessions/{session.id}/messages",
        headers=_headers(user),
        json={"content": "  "},
    )
    failed = client.post(
        f"/api/chat/sessions/{session.id}/messages",
        headers=_headers(user),
        json={"content": "Try again later"},
    )

    assert blank.status_code == 422
    assert failed.status_code == 503
    assert "private backend detail" not in failed.text
    assert db_session.query(ChatMessage).filter_by(session_id=session.id).count() == 0


def test_session_history_delete_and_user_only_listing(
    client: TestClient,
    db_session: Session,
) -> None:
    first_user = _create_user(db_session, "chat-history-first@example.com")
    second_user = _create_user(db_session, "chat-history-second@example.com")
    first_session = ChatSession(user_id=first_user.id, title="First")
    second_session = ChatSession(user_id=second_user.id, title="Second")
    db_session.add_all([first_session, second_session])
    db_session.flush()
    db_session.add(
        ChatMessage(
            session_id=first_session.id,
            role=MessageRole.USER,
            content="Previous message",
        )
    )
    db_session.commit()
    db_session.refresh(first_session)

    listed = client.get("/api/chat/sessions", headers=_headers(first_user))
    detail = client.get(
        f"/api/chat/sessions/{first_session.id}",
        headers=_headers(first_user),
    )
    deleted = client.delete(
        f"/api/chat/sessions/{first_session.id}",
        headers=_headers(first_user),
    )

    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["message_count"] == 1
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) == 1
    assert deleted.status_code == 204
    assert db_session.query(ChatMessage).filter_by(session_id=first_session.id).count() == 0
