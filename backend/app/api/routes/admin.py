import logging
import os
from datetime import datetime, timezone
from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user, get_db
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.auth_session import AuthSession
from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document, DocumentStatus
from app.models.user import User, UserRole
from app.schemas.admin import AdminSessionRead, AdminStatistics, AdminUserCreate, AdminUserPage
from app.schemas.user import UserRead, UserRoleUpdate, UserStatusUpdate
from app.services.chroma_service import delete_document_collection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


def _active_admins_for_update(db: Session) -> List[User]:
    """Locks active admin rows so concurrent changes cannot remove the final admin."""
    return list(
        db.scalars(
            select(User)
            .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
            .order_by(User.id)
            .with_for_update()
        ).all()
    )


def _remove_document_file(file_path: str) -> None:
    upload_root = os.path.realpath(settings.UPLOAD_DIR)
    resolved_path = os.path.realpath(file_path)
    try:
        contained = os.path.commonpath((upload_root, resolved_path)) == upload_root
    except ValueError:
        contained = False
    if not contained:
        raise ValueError("Document path is outside the configured upload directory.")
    if os.path.exists(resolved_path):
        os.remove(resolved_path)


def _cleanup_user_documents(documents: List[Document]) -> None:
    for document in documents:
        delete_document_collection(document.id)
        _remove_document_file(document.file_path)


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    data: AdminUserCreate,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Creates an active user or administrator account from the admin console."""
    normalized_email = data.email.strip().lower()
    existing_user = db.scalar(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists",
        )

    user = User(
        full_name=data.full_name,
        email=normalized_email,
        password_hash=get_password_hash(data.password),
        role=data.role,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Could not create user (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The account could not be created. Please retry.",
        ) from exc
    return user


@router.get("/users", response_model=AdminUserPage)
def list_users(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[Optional[str], Query(max_length=255)] = None,
    role: Optional[UserRole] = None,
    is_active: Optional[bool] = None,
) -> AdminUserPage:
    """Returns paginated users with optional name/email, role, and status filters."""
    query = select(User)
    count_query = select(func.count(User.id))
    if search and search.strip():
        term = f"%{search.strip()}%"
        predicate = User.full_name.ilike(term) | User.email.ilike(term)
        query = query.where(predicate)
        count_query = count_query.where(predicate)
    if role is not None:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active.is_(is_active))
        count_query = count_query.where(User.is_active.is_(is_active))

    total = db.scalar(count_query) or 0
    users = list(
        db.scalars(
            query.order_by(User.created_at.desc(), User.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return AdminUserPage(
        items=[UserRead.model_validate(user) for user in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/users/{user_id}/status", response_model=UserRead)
def update_user_status(
    user_id: int,
    data: UserStatusUpdate,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if user.role == UserRole.ADMIN and user.is_active and not data.is_active:
        active_admins = _active_admins_for_update(db)
        if len(active_admins) <= 1:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The last active administrator cannot be deactivated.",
            )

    user.is_active = data.is_active
    if not data.is_active:
        db.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == user.id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )
    try:
        db.commit()
        db.refresh(user)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Could not update user status (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The user status could not be updated. Please retry.",
        ) from exc
    return user


@router.patch("/users/{user_id}/role", response_model=UserRead)
def update_user_role(
    user_id: int,
    data: UserRoleUpdate,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if (
        user.role == UserRole.ADMIN
        and user.is_active
        and data.role != UserRole.ADMIN
    ):
        active_admins = _active_admins_for_update(db)
        if len(active_admins) <= 1:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The last active administrator cannot be demoted.",
            )

    user.role = data.role
    try:
        db.commit()
        db.refresh(user)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Could not update user role (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The user role could not be updated. Please retry.",
        ) from exc
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if user.role == UserRole.ADMIN and user.is_active:
        active_admins = _active_admins_for_update(db)
        if len(active_admins) <= 1:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The last active administrator cannot be deleted.",
            )

    documents = list(
        db.scalars(select(Document).where(Document.uploader_id == user.id)).all()
    )
    try:
        _cleanup_user_documents(documents)
    except Exception as exc:
        db.rollback()
        logger.error(
            "Could not clean up assets while deleting user %s (%s).",
            user_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The user could not be fully deleted. Please retry.",
        ) from exc

    try:
        db.delete(user)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error(
            "User assets were removed but the row remains for user %s (%s).",
            user_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User files were cleaned up, but the account could not be deleted. Please retry.",
        ) from exc


@router.get("/statistics", response_model=AdminStatistics)
def get_statistics(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> AdminStatistics:
    return AdminStatistics(
        users=db.scalar(select(func.count(User.id))) or 0,
        active_users=db.scalar(
            select(func.count(User.id)).where(User.is_active.is_(True))
        )
        or 0,
        documents=db.scalar(select(func.count(Document.id))) or 0,
        ready_documents=db.scalar(
            select(func.count(Document.id)).where(
                Document.status == DocumentStatus.READY
            )
        )
        or 0,
        chat_sessions=db.scalar(select(func.count(ChatSession.id))) or 0,
        chat_messages=db.scalar(select(func.count(ChatMessage.id))) or 0,
    )


@router.get("/sessions", response_model=List[AdminSessionRead])
def list_all_sessions(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> List[dict[str, Any]]:
    """Lists all sessions read-only, excluding private chat message contents."""
    rows = db.execute(
        select(
            ChatSession,
            User.email,
            Document.title,
            func.count(ChatMessage.id).label("message_count"),
        )
        .join(User, ChatSession.user_id == User.id)
        .outerjoin(Document, ChatSession.document_id == Document.id)
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .group_by(ChatSession.id, User.email, Document.title)
        .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [
        {
            "id": chat_session.id,
            "user_id": chat_session.user_id,
            "user_email": email,
            "document_id": chat_session.document_id,
            "document_title": document_title,
            "title": chat_session.title,
            "message_count": message_count,
            "created_at": chat_session.created_at,
            "updated_at": chat_session.updated_at,
        }
        for chat_session, email, document_title, message_count in rows
    ]
