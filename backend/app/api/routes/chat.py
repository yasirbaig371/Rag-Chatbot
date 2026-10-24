import logging
from datetime import datetime, timezone
from typing import Annotated, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_active_user, get_db
from app.core.rate_limit import limiter
from app.models.chat import ChatMessage, ChatSession, MessageRole
from app.models.document import Document
from app.models.user import User
from app.schemas.chat import (
    ChatMessageCreate,
    ChatMessageRead,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionSummary,
)
from app.services.llm_service import LLMServiceError
from app.services.rag_service import answer_rag_query, get_accessible_documents

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


def _get_owned_session(db: Session, session_id: int, user_id: int) -> ChatSession | None:
    return db.scalar(
        select(ChatSession)
        .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .options(selectinload(ChatSession.messages))
    )


@router.post(
    "/sessions",
    response_model=ChatSessionDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_chat_session(
    data: ChatSessionCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Creates a session bound to an accessible ready document or to all accessible documents."""
    document_title = None
    if data.document_id is not None:
        documents = get_accessible_documents(
            db,
            current_user,
            target_document_id=data.document_id,
        )
        if not documents:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found.",
            )
        document_title = documents[0].title

    chat_session = ChatSession(
        user_id=current_user.id,
        document_id=data.document_id,
        title="New Chat",
    )
    db.add(chat_session)
    try:
        db.commit()
        db.refresh(chat_session)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Could not create a chat session (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The chat session could not be created. Please try again.",
        ) from exc
    return {
        "id": chat_session.id,
        "document_id": chat_session.document_id,
        "document_title": document_title,
        "title": chat_session.title,
        "created_at": chat_session.created_at,
        "updated_at": chat_session.updated_at,
        "messages": [],
    }


@router.get("/sessions", response_model=List[ChatSessionSummary])
def list_chat_sessions(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> List[dict[str, Any]]:
    """Lists only the current user's sessions, newest activity first."""
    rows = db.execute(
        select(
            ChatSession,
            Document.title,
            func.count(ChatMessage.id).label("message_count"),
        )
        .outerjoin(Document, ChatSession.document_id == Document.id)
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.user_id == current_user.id)
        .group_by(ChatSession.id, Document.title)
        .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    results: List[dict[str, Any]] = []
    for chat_session, document_title, message_count in rows:
        if chat_session.document_id is not None:
            accessible = get_accessible_documents(
                db,
                current_user,
                target_document_id=chat_session.document_id,
            )
            if not accessible:
                document_title = None
        results.append(
            {
                "id": chat_session.id,
                "document_id": chat_session.document_id,
                "document_title": document_title,
                "title": chat_session.title,
                "message_count": message_count,
                "created_at": chat_session.created_at,
                "updated_at": chat_session.updated_at,
            }
        )
    return results


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_chat_session(
    session_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Returns a session and its messages only to its owner."""
    chat_session = _get_owned_session(db, session_id, current_user.id)
    if chat_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found.",
        )

    document_title = None
    if chat_session.document_id is not None:
        documents = get_accessible_documents(
            db,
            current_user,
            target_document_id=chat_session.document_id,
        )
        if not documents:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found.",
            )
        document_title = documents[0].title

    return {
        "id": chat_session.id,
        "document_id": chat_session.document_id,
        "document_title": document_title,
        "title": chat_session.title,
        "created_at": chat_session.created_at,
        "updated_at": chat_session.updated_at,
        "messages": chat_session.messages,
    }


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageResponse,
)
@limiter.limit("10/minute")
def send_chat_message(
    request: Request,
    session_id: int,
    data: ChatMessageCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, ChatMessage]:
    """Answers a query with RAG and persists both messages only after generation succeeds."""
    chat_session = _get_owned_session(db, session_id, current_user.id)
    if chat_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found.",
        )

    if chat_session.document_id is not None:
        documents = get_accessible_documents(
            db,
            current_user,
            target_document_id=chat_session.document_id,
        )
        if not documents:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found.",
            )

    history = [
        {"role": message.role.value, "content": message.content}
        for message in chat_session.messages[-4:]
    ]
    try:
        answer, sources = answer_rag_query(
            db=db,
            user=current_user,
            query_text=data.content,
            target_document_id=chat_session.document_id,
            conversation_history=history,
        )
    except LLMServiceError as exc:
        logger.warning("LLM request failed for a chat session (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assistant is temporarily unavailable. Your message was not saved; please retry.",
        ) from exc
    except Exception as exc:
        logger.error("RAG query failed for a chat session (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assistant could not complete this request. Your message was not saved; please retry.",
        ) from exc

    user_message = ChatMessage(
        session_id=chat_session.id,
        role=MessageRole.USER,
        content=data.content,
    )
    assistant_message = ChatMessage(
        session_id=chat_session.id,
        role=MessageRole.ASSISTANT,
        content=answer,
        sources=sources,
    )
    if not any(message.role == MessageRole.USER for message in chat_session.messages):
        chat_session.title = data.content[:255]
    chat_session.updated_at = datetime.now(timezone.utc)
    db.add_all([user_message, assistant_message])
    try:
        db.commit()
        db.refresh(user_message)
        db.refresh(assistant_message)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Could not save a chat exchange (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assistant responded, but the exchange could not be saved. Please retry.",
        ) from exc

    return {
        "user_message": user_message,
        "assistant_message": assistant_message,
    }


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_chat_session(
    session_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Deletes a session and its messages only when owned by the current user."""
    chat_session = db.scalar(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    if chat_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found.",
        )
    try:
        db.delete(chat_session)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Could not delete a chat session (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The chat session could not be deleted. Please try again.",
        ) from exc
