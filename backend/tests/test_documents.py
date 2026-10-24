from pathlib import Path
from typing import Any
from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.chat import ChatSession
from app.models.document import Document, DocumentStatus
from app.models.user import User, UserRole
from app.api.routes import documents as documents_routes


def _create_user(db: Session, email: str, role: UserRole) -> User:
    user = User(
        full_name=email.split("@")[0],
        email=email,
        password_hash="not-used-by-these-tests",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(subject=user.id, role=user.role.value)
    return {"Authorization": f"Bearer {token}"}


def _create_document(
    db: Session,
    uploader: User,
    *,
    title: str,
    is_public: bool,
    file_path: str,
    file_hash: str,
    status: DocumentStatus = DocumentStatus.READY,
) -> Document:
    document = Document(
        title=title,
        filename=f"{title}.pdf",
        file_path=file_path,
        uploader_id=uploader.id,
        is_public=is_public,
        chroma_collection="pending",
        chunk_count=1,
        page_count=1,
        file_hash=file_hash,
        status=status,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def _mock_pdf_processing(monkeypatch: Any, tmp_path: Path, file_hash: str) -> None:
    monkeypatch.setattr(
        documents_routes,
        "read_and_validate_pdf_stream",
        lambda stream, filename, content_type: (b"%PDF-1.7 mocked", file_hash),
    )
    monkeypatch.setattr(
        documents_routes,
        "extract_text_by_page",
        lambda file_bytes: [(1, "Evidence from page one."), (2, "")],
    )

    def save_pdf(file_bytes: bytes) -> tuple[str, str]:
        path = tmp_path / "stored.pdf"
        path.write_bytes(file_bytes)
        return str(path), path.name

    monkeypatch.setattr(documents_routes, "save_pdf_to_disk", save_pdf)


def _text_pdf_bytes() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): font_reference}
            )
        }
    )
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 72 720 Td (A real uploaded PDF.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_admin_upload_indexes_pdf_and_defaults_to_public(
    client: TestClient,
    db_session: Session,
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    admin = _create_user(db_session, "document-admin@example.com", UserRole.ADMIN)
    _mock_pdf_processing(monkeypatch, tmp_path, "a" * 64)
    indexed: dict[str, Any] = {}
    monkeypatch.setattr(
        documents_routes,
        "add_document_chunks",
        lambda **kwargs: indexed.update(kwargs),
    )

    response = client.post(
        "/api/documents/upload",
        headers=_auth_headers(admin),
        files={"file": ("source.pdf", b"%PDF-1.7 mocked", "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ready"
    assert body["is_public"] is True
    assert body["filename"] == "source.pdf"
    assert body["page_count"] == 2
    assert body["chunk_count"] == 1
    assert body["chroma_collection"] == f"doc_{body['id']}"
    assert "file_path" not in body
    assert indexed["metadatas"][0]["page"] == 1
    assert (tmp_path / "stored.pdf").exists()


def test_real_text_pdf_is_saved_and_indexed_before_success_response(
    client: TestClient,
    db_session: Session,
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    admin = _create_user(db_session, "real-pdf-admin@example.com", UserRole.ADMIN)
    monkeypatch.setattr(documents_routes.settings, "UPLOAD_DIR", str(tmp_path))
    indexed: dict[str, Any] = {}
    monkeypatch.setattr(
        documents_routes,
        "add_document_chunks",
        lambda **kwargs: indexed.update(kwargs),
    )

    response = client.post(
        "/api/documents/upload",
        headers=_auth_headers(admin),
        data={"is_public": "false"},
        files={
            "file": (
                r"C:\client\report.pdf",
                _text_pdf_bytes(),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ready"
    assert body["is_public"] is False
    assert body["filename"] == "report.pdf"
    assert body["page_count"] == 1
    assert body["chunk_count"] == 1
    assert indexed["chunk_texts"] == ["A real uploaded PDF."]
    assert indexed["metadatas"][0]["page"] == 1
    assert len(list(tmp_path.glob("*.pdf"))) == 1


def test_user_sees_only_public_ready_documents_and_private_get_is_not_found(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = _create_user(db_session, "visibility-admin@example.com", UserRole.ADMIN)
    user = _create_user(db_session, "visibility-user@example.com", UserRole.USER)
    public_doc = _create_document(
        db_session,
        admin,
        title="Public",
        is_public=True,
        file_path="not-used-public.pdf",
        file_hash="b" * 64,
    )
    private_doc = _create_document(
        db_session,
        admin,
        title="Private",
        is_public=False,
        file_path="not-used-private.pdf",
        file_hash="c" * 64,
    )

    response = client.get("/api/documents", headers=_auth_headers(user))
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [public_doc.id]
    assert client.get(
        f"/api/documents/{private_doc.id}",
        headers=_auth_headers(user),
    ).status_code == 404

    admin_response = client.get("/api/documents", headers=_auth_headers(admin))
    assert {item["id"] for item in admin_response.json()} == {public_doc.id, private_doc.id}
    visibility_response = client.patch(
        f"/api/documents/{private_doc.id}/visibility",
        headers=_auth_headers(admin),
        json={"is_public": True},
    )
    assert visibility_response.status_code == 200
    assert visibility_response.json()["is_public"] is True


def test_duplicate_upload_is_rejected_before_file_storage(
    client: TestClient,
    db_session: Session,
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    admin = _create_user(db_session, "duplicate-admin@example.com", UserRole.ADMIN)
    _create_document(
        db_session,
        admin,
        title="Existing",
        is_public=True,
        file_path="existing.pdf",
        file_hash="d" * 64,
    )
    _mock_pdf_processing(monkeypatch, tmp_path, "d" * 64)
    monkeypatch.setattr(
        documents_routes,
        "save_pdf_to_disk",
        lambda _: (_ for _ in ()).throw(AssertionError("duplicate was stored")),
    )

    response = client.post(
        "/api/documents/upload",
        headers=_auth_headers(admin),
        files={"file": ("duplicate.pdf", b"%PDF-1.7 mocked", "application/pdf")},
    )

    assert response.status_code == 409
    assert "already been uploaded" in response.json()["detail"]


def test_failed_indexing_is_recorded_and_partial_collection_is_cleaned(
    client: TestClient,
    db_session: Session,
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    admin = _create_user(db_session, "failed-index-admin@example.com", UserRole.ADMIN)
    file_hash = "e" * 64
    _mock_pdf_processing(monkeypatch, tmp_path, file_hash)
    monkeypatch.setattr(
        documents_routes,
        "add_document_chunks",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("internal path must not leak")),
    )
    deleted: list[int] = []
    monkeypatch.setattr(
        documents_routes,
        "delete_document_collection",
        lambda document_id: deleted.append(document_id),
    )

    response = client.post(
        "/api/documents/upload",
        headers=_auth_headers(admin),
        data={"is_public": "false"},
        files={"file": ("failed.pdf", b"%PDF-1.7 mocked", "application/pdf")},
    )

    assert response.status_code == 503
    assert "internal path must not leak" not in response.text
    failed_document = db_session.scalar(
        select(Document).where(Document.file_hash == file_hash)
    )
    assert failed_document is not None
    assert failed_document.status == DocumentStatus.FAILED
    assert failed_document.is_public is False
    assert failed_document.processing_error is not None
    assert deleted == [failed_document.id]


def test_document_delete_removes_assets_and_unlinks_chat_session(
    client: TestClient,
    db_session: Session,
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    admin = _create_user(db_session, "delete-admin@example.com", UserRole.ADMIN)
    monkeypatch.setattr(documents_routes.settings, "UPLOAD_DIR", str(tmp_path))
    pdf_path = tmp_path / "to-delete.pdf"
    pdf_path.write_bytes(b"%PDF-1.7")
    document = _create_document(
        db_session,
        admin,
        title="Delete Me",
        is_public=True,
        file_path=str(pdf_path),
        file_hash="f" * 64,
    )
    chat_session = ChatSession(user_id=admin.id, document_id=document.id, title="History")
    db_session.add(chat_session)
    db_session.commit()
    db_session.refresh(chat_session)
    cleaned: list[int] = []
    monkeypatch.setattr(
        documents_routes,
        "delete_document_collection",
        lambda document_id: cleaned.append(document_id),
    )

    response = client.delete(
        f"/api/documents/{document.id}",
        headers=_auth_headers(admin),
    )

    assert response.status_code == 204
    assert not pdf_path.exists()
    assert cleaned == [document.id]
    db_session.expire_all()
    assert db_session.get(Document, document.id) is None
    assert db_session.get(ChatSession, chat_session.id).document_id is None
