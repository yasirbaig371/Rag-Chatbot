import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
from typing import Any, Dict, List, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
import google.generativeai as genai

from app.core.config import settings

# Global singleton handles
_chroma_client: Optional[chromadb.PersistentClient] = None
_configured_api_key: Optional[str] = None


def get_chroma_client() -> chromadb.PersistentClient:
    """Returns persistent ChromaDB client instance, ensuring target storage directory exists."""
    global _chroma_client
    if _chroma_client is None:
        os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _chroma_client


def configure_embedding_api() -> None:
    """Configures the Gemini API when a key is available."""
    global _configured_api_key
    api_key = settings.GEMINI_API_KEY
    if api_key and api_key != _configured_api_key:
        genai.configure(api_key=api_key)
        _configured_api_key = api_key


def _embed_content(text: str, task_type: str) -> List[float]:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY must be set to generate embeddings.")

    configure_embedding_api()
    response = genai.embed_content(
        model=settings.EMBEDDING_MODEL_NAME,
        content=text,
        task_type=task_type,
        output_dimensionality=768,
    )
    return [float(value) for value in response["embedding"]]


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Generates Gemini retrieval-document embeddings for input texts."""
    return [_embed_content(text, "retrieval_document") for text in texts]


def embed_query(query: str) -> List[float]:
    """Generates embedding for a single search query."""
    return _embed_content(query, "retrieval_query")


def get_collection_name(document_id: int) -> str:
    """Returns standard collection identifier for a document: doc_{document_id}."""
    return f"doc_{document_id}"


def get_or_create_collection(document_id: int) -> Any:
    """Gets or creates the Chroma collection for a document using cosine distance metric."""
    client = get_chroma_client()
    col_name = get_collection_name(document_id)
    return client.get_or_create_collection(
        name=col_name,
        metadata={"hnsw:space": "cosine"},
    )


def add_document_chunks(
    document_id: int,
    chunk_ids: List[str],
    chunk_texts: List[str],
    metadatas: List[Dict[str, Any]],
) -> None:
    """Embeds and inserts text chunks into the document's Chroma collection."""
    if not chunk_texts:
        return

    collection = get_or_create_collection(document_id)
    embeddings = embed_texts(chunk_texts)
    collection.add(
        ids=chunk_ids,
        documents=chunk_texts,
        metadatas=metadatas,
        embeddings=embeddings,
    )


def delete_document_collection(document_id: int) -> bool:
    """Drops a document collection, returning False only when it did not exist."""
    client = get_chroma_client()
    col_name = get_collection_name(document_id)
    collections = client.list_collections()
    if not any(collection.name == col_name for collection in collections):
        return False
    client.delete_collection(name=col_name)
    return True


def query_single_collection(
    document_id: int,
    query_embedding: List[float],
    top_k: int = 4,
) -> List[Dict[str, Any]]:
    """Queries an individual document collection with a query embedding."""
    client = get_chroma_client()
    col_name = get_collection_name(document_id)
    try:
        collection = client.get_collection(name=col_name)
    except Exception:
        return []

    count = collection.count()
    if count == 0:
        return []

    n_results = min(top_k, count)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    chunks: List[Dict[str, Any]] = []
    if not results or not results["ids"] or not results["ids"][0]:
        return chunks

    ids = results["ids"][0]
    docs = results["documents"][0] if results.get("documents") else []
    metas = results["metadatas"][0] if results.get("metadatas") else []
    dists = results["distances"][0] if results.get("distances") else []

    for i in range(len(ids)):
        chunks.append({
            "id": ids[i],
            "text": docs[i] if i < len(docs) else "",
            "metadata": metas[i] if i < len(metas) else {},
            "distance": float(dists[i]) if i < len(dists) else 1.0,
        })
    return chunks
