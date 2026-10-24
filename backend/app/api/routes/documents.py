import logging
import os
from typing import Annotated, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_current_admin_user, get_db
from app.core.config import settings
from app.core.rate_limit import limiter
from app.models.document import Document, DocumentStatus
from app.models.user import User, UserRole
from app.schemas.document import DocumentRead, DocumentVisibilityUpdate
from app.services.chroma_service import add_document_chunks, delete_document_collection, get_collection_name
from app.services.pdf_service import (
    PDFEmptyError,
    PDFSizeLimitError,
    PDFValidationError,
    chunk_pages,
    extract_text_by_page,
    read_and_validate_pdf_stream,
    sanitize_filename,
    save_pdf_to_disk,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


def _visible_document(db: Session, document_id: int, user: User) -> Document | None:
    query = select(Document).where(Document.id == document_id)
    if user.role != UserRole.ADMIN:
        query = query.where(
            Document.is_public.is_(True),
            Document.status == DocumentStatus.READY,
        )
    return db.scalar(query)


def _remove_uploaded_file(file_path: str) -> None:
    upload_root = os.path.realpath(settings.UPLOAD_DIR)
    resolved_path = os.path.realpath(file_path)
    try:
        is_within_upload_dir = os.path.commonpath((upload_root, resolved_path)) == upload_root
    except ValueError:
        is_within_upload_dir = False

    if not is_within_upload_dir:
        raise ValueError("Document path is outside the configured upload directory.")
    if os.path.exists(resolved_path):
        os.remove(resolved_path)


def _cleanup_document_assets(document: Document) -> None:
    delete_document_collection(document.id)
    _remove_uploaded_file(document.file_path)


@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=255),
    is_public: bool = Form(default=True),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> Document:
    """Validates, stores, and indexes one PDF before returning a ready document."""
    try:
        if file.content_type != "application/pdf":
            raise PDFValidationError("Invalid MIME type. Only application/pdf is supported.")
        file_bytes, file_hash = read_and_validate_pdf_stream(
            file.file,
            file.filename or "",
            file.content_type,
        )
        pages = extract_text_by_page(file_bytes)
    except PDFSizeLimitError as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc
    except PDFEmptyError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except PDFValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    finally:
        file.file.close()

    existing_document_id = db.scalar(
        select(Document.id).where(
            Document.file_hash == file_hash,
            Document.status != DocumentStatus.FAILED,
        )
    )
    if existing_document_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This PDF has already been uploaded.",
        )

    display_filename = sanitize_filename(file.filename or "")
    document_title = (title if title is not None else os.path.splitext(display_filename)[0]).strip()
    if not document_title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Document title cannot be blank.",
        )

    try:
        file_path, _ = save_pdf_to_disk(file_bytes)
    except OSError as exc:
        logger.error("Could not store an uploaded PDF (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The PDF could not be stored. Please try again.",
        ) from exc
    document = Document(
        title=document_title,
        filename=display_filename,
        file_path=file_path,
        uploader_id=current_user.id,
        is_public=is_public,
        chroma_collection="pending",
        chunk_count=0,
        page_count=len(pages),
        file_hash=file_hash,
        status=DocumentStatus.PROCESSING,
    )
    try:
        db.add(document)
        db.commit()
        db.refresh(document)
    except SQLAlchemyError as exc:
        db.rollback()
        try:
            _remove_uploaded_file(file_path)
        except OSError:
            logger.error("Could not clean up an unregistered uploaded PDF.")
        logger.error("Could not create a document record (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The document could not be saved. Please try again.",
        ) from exc

    document.chroma_collection = get_collection_name(document.id)
    try:
        db.commit()
        chunks = chunk_pages(pages, document.id, document.title)
        add_document_chunks(
            document_id=document.id,
            chunk_ids=[chunk["id"] for chunk in chunks],
            chunk_texts=[chunk["text"] for chunk in chunks],
            metadatas=[chunk["metadata"] for chunk in chunks],
        )
        document.chunk_count = len(chunks)
        document.status = DocumentStatus.READY
        document.processing_error = None
        db.commit()
        db.refresh(document)
        return document
    except Exception as exc:
        db.rollback()
        logger.error(
            "Indexing failed for document %s (%s).",
            document.id,
            type(exc).__name__,
        )
        try:
            delete_document_collection(document.id)
        except Exception as cleanup_exc:
            logger.error(
                "Could not clean up the index for document %s (%s).",
                document.id,
                type(cleanup_exc).__name__,
            )
        failed_document = db.get(Document, document.id)
        if failed_document is not None:
            failed_document.status = DocumentStatus.FAILED
            failed_document.processing_error = "Indexing failed. Please delete this item and upload the PDF again."
            try:
                db.commit()
            except SQLAlchemyError as db_exc:
                db.rollback()
                logger.error(
                    "Could not save failed state for document %s (%s).",
                    document.id,
                    type(db_exc).__name__,
                )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The PDF was received but could not be indexed. Please try again later.",
        ) from exc


@router.get("", response_model=List[DocumentRead])
def list_documents(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> List[Document]:
    """Lists all documents for admins and ready public documents for regular users."""
    query = select(Document)
    if current_user.role != UserRole.ADMIN:
        query = query.where(
            Document.is_public.is_(True),
            Document.status == DocumentStatus.READY,
        )
    return list(
        db.scalars(
            query.order_by(Document.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Document:
    """Returns a document only when it is visible to the current caller."""
    document = _visible_document(db, document_id, current_user)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document


@router.patch("/{document_id}/visibility", response_model=DocumentRead)
def update_document_visibility(
    document_id: int,
    data: DocumentVisibilityUpdate,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    document.is_public = data.is_public
    db.commit()
    db.refresh(document)
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Removes the PDF and vector collection before deleting its row.

    If the database commit fails, the row remains and this endpoint can be
    retried; both asset-cleanup operations are safe when assets are absent.
    """
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    try:
        _cleanup_document_assets(document)
    except Exception as exc:
        logger.error(
            "Could not clean up assets for document %s (%s).",
            document_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The document could not be fully deleted. Please retry.",
        ) from exc

    try:
        db.delete(document)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error(
            "Assets were removed but the row remains for document %s (%s).",
            document_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document files were cleaned up, but its record could not be deleted. Please retry.",
        ) from exc
