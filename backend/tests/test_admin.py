from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes import admin as admin_routes
from app.core.security import create_access_token, hash_token
from app.models.auth_session import AuthSession
from app.models.chat import ChatMessage, ChatSession, MessageRole
from app.models.document import Document, DocumentStatus
from app.models.user import User, UserRole


def _create_user(
    db: Session,
    email: str,
    role: UserRole = UserRole.USER,
    *,
    active: bool = True,
) -> User:
    user = User(
        full_name=email.split("@")[0],
        email=email,
        password_hash="test-hash",
        role=role,
        is_active=active,
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
    file_path: str = "unused.pdf",
) -> Document:
    document = Document(
        title=title,
        filename=f"{title}.pdf",
        file_path=file_path,
        uploader_id=uploader.id,
        is_public=True,
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


def test_admin_user_list_supports_pagination_search_and_filters(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _create_user(db_session, "users-admin@example.com", UserRole.ADMIN)
    _create_user(db_session, "alice@example.com")
    _create_user(db_session, "bob@example.com", active=False)
    _create_user(db_session, "other-admin@example.com", UserRole.ADMIN)

    denied = client.get("/api/admin/users", headers=_headers(_create_user(db_session, "regular@example.com")))
    assert denied.status_code == 403

    response = client.get(
        "/api/admin/users?search=alice&role=user&is_active=true&limit=1&offset=0",
        headers=_headers(admin),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 1
    assert body["items"][0]["email"] == "alice@example.com"
    assert "password_hash" not in body["items"][0]

    invalid_pagination = client.get(
        "/api/admin/users?limit=0",
        headers=_headers(admin),
    )
    assert invalid_pagination.status_code == 422


def test_admin_can_create_user_or_admin_accounts(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _create_user(db_session, "create-admin@example.com", UserRole.ADMIN)
    headers = _headers(admin)
    payload = {
        "full_name": "New Standard User",
        "email": "New.User@Example.com",
        "password": "SecurePassword123!",
        "role": "user",
    }

    user_response = client.post("/api/admin/users", headers=headers, json=payload)
    assert user_response.status_code == 201
    user_body = user_response.json()
    assert user_body["email"] == "new.user@example.com"
    assert user_body["role"] == "user"
    assert "password_hash" not in user_body
    created_user = db_session.get(User, user_body["id"])
    assert created_user is not None
    assert created_user.password_hash != payload["password"]

    payload.update(
        full_name="New Administrator",
        email="new.admin@example.com",
        role="admin",
    )
    admin_response = client.post("/api/admin/users", headers=headers, json=payload)
    assert admin_response.status_code == 201
    assert admin_response.json()["role"] == "admin"

    duplicate_response = client.post(
        "/api/admin/users",
        headers=headers,
        json={**payload, "email": "NEW.ADMIN@example.com"},
    )
    assert duplicate_response.status_code == 400


def test_regular_user_cannot_create_role_based_accounts(
    client: TestClient,
    db_session: Session,
) -> None:
    user = _create_user(db_session, "regular-create@example.com")
    response = client.post(
        "/api/admin/users",
        headers=_headers(user),
        json={
            "full_name": "Attempted Admin",
            "email": "attempted-admin@example.com",
            "password": "SecurePassword123!",
            "role": "admin",
        },
    )
    assert response.status_code == 403


def test_cannot_deactivate_demote_or_delete_last_active_admin(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _create_user(db_session, "sole-admin@example.com", UserRole.ADMIN)
    headers = _headers(admin)

    deactivate = client.patch(
        f"/api/admin/users/{admin.id}/status",
        headers=headers,
        json={"is_active": False},
    )
    demote = client.patch(
        f"/api/admin/users/{admin.id}/role",
        headers=headers,
        json={"role": "user"},
    )
    delete = client.delete(f"/api/admin/users/{admin.id}", headers=headers)

    assert deactivate.status_code == 409
    assert demote.status_code == 409
    assert delete.status_code == 409
    assert db_session.get(User, admin.id).role == UserRole.ADMIN
    assert db_session.get(User, admin.id).is_active is True


def test_admin_status_role_changes_and_refresh_revocation(
    client: TestClient,
    db_session: Session,
) -> None:
    current_admin = _create_user(db_session, "status-admin@example.com", UserRole.ADMIN)
    target_admin = _create_user(db_session, "target-admin@example.com", UserRole.ADMIN)
    inactive_admin = _create_user(
        db_session,
        "inactive-admin@example.com",
        UserRole.ADMIN,
        active=False,
    )
    auth_session = AuthSession(
        user_id=target_admin.id,
        token_hash=hash_token("raw-refresh-token"),
        expires_at=datetime.now(timezone.utc),
    )
    db_session.add(auth_session)
    db_session.commit()

    demote = client.patch(
        f"/api/admin/users/{target_admin.id}/role",
        headers=_headers(current_admin),
        json={"role": "user"},
    )
    assert demote.status_code == 200
    assert demote.json()["role"] == "user"

    deactivate = client.patch(
        f"/api/admin/users/{inactive_admin.id}/status",
        headers=_headers(current_admin),
        json={"is_active": False},
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False

    reactivate = client.patch(
        f"/api/admin/users/{inactive_admin.id}/status",
        headers=_headers(current_admin),
        json={"is_active": True},
    )
    assert reactivate.status_code == 200
    assert reactivate.json()["is_active"] is True

    target_admin = db_session.get(User, target_admin.id)
    target_admin.role = UserRole.ADMIN
    db_session.commit()
    revoke = client.patch(
        f"/api/admin/users/{target_admin.id}/status",
        headers=_headers(current_admin),
        json={"is_active": False},
    )
    assert revoke.status_code == 200
    db_session.refresh(auth_session)
    assert auth_session.revoked_at is not None


def test_admin_statistics_and_read_only_sessions(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _create_user(db_session, "statistics-admin@example.com", UserRole.ADMIN)
    user = _create_user(db_session, "statistics-user@example.com")
    document = _create_document(db_session, admin, title="Statistics doc")
    session = ChatSession(user_id=user.id, document_id=document.id, title="My chat")
    db_session.add(session)
    db_session.flush()
    db_session.add_all(
        [
            ChatMessage(session_id=session.id, role=MessageRole.USER, content="Question"),
            ChatMessage(session_id=session.id, role=MessageRole.ASSISTANT, content="Answer"),
        ]
    )
    db_session.commit()

    statistics = client.get("/api/admin/statistics", headers=_headers(admin))
    assert statistics.status_code == 200
    assert statistics.json() == {
        "users": 2,
        "active_users": 2,
        "documents": 1,
        "ready_documents": 1,
        "chat_sessions": 1,
        "chat_messages": 2,
    }

    sessions = client.get("/api/admin/sessions", headers=_headers(admin))
    assert sessions.status_code == 200
    assert len(sessions.json()) == 1
    result = sessions.json()[0]
    assert result["user_email"] == user.email
    assert result["document_title"] == document.title
    assert result["message_count"] == 2
    assert "messages" not in result
    assert "content" not in result


def test_delete_user_cleans_documents_and_cascades_history(
    client: TestClient,
    db_session: Session,
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    admin = _create_user(db_session, "delete-user-admin@example.com", UserRole.ADMIN)
    target = _create_user(db_session, "delete-target@example.com")
    file_path = tmp_path / "target-document.pdf"
    file_path.write_bytes(b"%PDF-1.7")
    document = _create_document(
        db_session,
        target,
        title="Target",
        file_path=str(file_path),
    )
    session = ChatSession(user_id=target.id, document_id=document.id)
    db_session.add(session)
    db_session.flush()
    message = ChatMessage(
        session_id=session.id,
        role=MessageRole.USER,
        content="Keep only for cascading test",
    )
    db_session.add(message)
    db_session.commit()
    db_session.refresh(session)
    db_session.refresh(message)
    monkeypatch.setattr(admin_routes.settings, "UPLOAD_DIR", str(tmp_path))
    cleaned: list[int] = []
    monkeypatch.setattr(
        admin_routes,
        "delete_document_collection",
        lambda document_id: cleaned.append(document_id),
    )

    response = client.delete(
        f"/api/admin/users/{target.id}",
        headers=_headers(admin),
    )

    assert response.status_code == 204
    assert not file_path.exists()
    assert cleaned == [document.id]
    assert db_session.get(User, target.id) is None
    assert db_session.get(Document, document.id) is None
    assert db_session.get(ChatSession, session.id) is None
    assert db_session.get(ChatMessage, message.id) is None


def test_unknown_user_admin_actions_return_not_found(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _create_user(db_session, "unknown-admin@example.com", UserRole.ADMIN)
    headers = _headers(admin)

    role = client.patch(
        "/api/admin/users/987654/role",
        headers=headers,
        json={"role": "user"},
    )
    status_update = client.patch(
        "/api/admin/users/987654/status",
        headers=headers,
        json={"is_active": False},
    )
    delete = client.delete("/api/admin/users/987654", headers=headers)

    assert role.status_code == status_update.status_code == delete.status_code == 404
