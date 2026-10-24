import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.models.user import User, UserRole
from app.services.chroma_service import embed_query, query_single_collection
from app.services.llm_service import generate_rag_answer

GREETING_RESPONSES = {
    "good afternoon",
    "good evening",
    "good morning",
    "greetings",
    "hello",
    "hello there",
    "hey",
    "hey there",
    "hi",
    "hi there",
}


def is_greeting(query_text: str) -> bool:
    normalized = " ".join(re.sub(r"[^\w\s]", "", query_text.casefold()).split())
    return normalized in GREETING_RESPONSES


def get_accessible_documents(
    db: Session,
    user: User,
    target_document_id: Optional[int] = None,
) -> List[Document]:
    """Retrieves list of documents accessible to the given user.

    ADMIN: All documents with status READY.
    USER: Only public documents (is_public=True) with status READY.
    """
    query = select(Document).where(Document.status == DocumentStatus.READY)

    if user.role != UserRole.ADMIN:
        query = query.where(Document.is_public.is_(True))

    if target_document_id is not None:
        query = query.where(Document.id == target_document_id)

    return list(db.scalars(query).all())


def retrieve_relevant_chunks(
    db: Session,
    user: User,
    query_text: str,
    target_document_id: Optional[int] = None,
    top_k: int = 4,
    distance_threshold: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Gathers candidate chunks from authorized collections, merges and ranks them globally by cosine distance."""
    documents = get_accessible_documents(db, user, target_document_id=target_document_id)
    if not documents:
        return []

    threshold = distance_threshold if distance_threshold is not None else settings.RAG_DISTANCE_THRESHOLD
    query_vec = embed_query(query_text)

    all_candidates: List[Dict[str, Any]] = []

    # Gather top candidates from each accessible document
    for doc in documents:
        doc_chunks = query_single_collection(
            document_id=doc.id,
            query_embedding=query_vec,
            top_k=top_k,
        )
        for chunk in doc_chunks:
            # Inject document title and ID if missing from metadata
            chunk.setdefault("metadata", {})
            chunk["metadata"].setdefault("document_id", doc.id)
            chunk["metadata"].setdefault("title", doc.title)

            # Cosine distance filtering: only keep chunks below the threshold
            if chunk.get("distance", 1.0) <= threshold:
                all_candidates.append(chunk)

    # Sort globally by distance ascending (lower distance = higher semantic similarity)
    all_candidates.sort(key=lambda c: c.get("distance", 1.0))

    # Return global top-k
    return all_candidates[:top_k]


def answer_rag_query(
    db: Session,
    user: User,
    query_text: str,
    target_document_id: Optional[int] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Orchestrates end-to-end RAG retrieval, thresholding, and LLM answer generation."""
    if is_greeting(query_text):
        return "Hello! How can I help you with your documents today?", []

    # 1. Retrieve top chunks
    chunks = retrieve_relevant_chunks(
        db=db,
        user=user,
        query_text=query_text,
        target_document_id=target_document_id,
        top_k=settings.RAG_TOP_K,
        distance_threshold=settings.RAG_DISTANCE_THRESHOLD,
    )

    # 2. Strict threshold fallback: do not call LLM if no relevant evidence is found
    if not chunks:
        return "I couldn't find this information in the available documents.", []

    # 3. Call OpenRouter LLM service with grounded context
    answer, sources = generate_rag_answer(
        query=query_text,
        retrieved_chunks=chunks,
        conversation_history=conversation_history,
    )
    return answer, sources
