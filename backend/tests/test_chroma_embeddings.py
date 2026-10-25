from typing import Any

import pytest

from app.core.config import settings
from app.services import chroma_service


def test_embedding_model_default_is_supported_gemini_model() -> None:
    from app.core.config import Settings

    assert Settings(_env_file=None).EMBEDDING_MODEL_NAME == "models/gemini-embedding-001"


def test_embed_texts_uses_gemini_retrieval_document_embeddings(
    monkeypatch: Any,
) -> None:
    calls: list[dict[str, Any]] = []
    configured_keys: list[str] = []

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr(chroma_service, "_configured_api_key", None)
    monkeypatch.setattr(
        chroma_service.genai,
        "configure",
        lambda *, api_key: configured_keys.append(api_key),
    )

    def embed_content(**kwargs: Any) -> dict[str, list[float]]:
        calls.append(kwargs)
        return {"embedding": [0.25, 0.75]}

    monkeypatch.setattr(chroma_service.genai, "embed_content", embed_content)

    embeddings = chroma_service.embed_texts(["first", "second"])

    assert embeddings == [[0.25, 0.75], [0.25, 0.75]]
    assert all(type(value) is float for vector in embeddings for value in vector)
    assert configured_keys == ["test-gemini-key"]
    assert [call["content"] for call in calls] == ["first", "second"]
    assert all(call["model"] == settings.EMBEDDING_MODEL_NAME for call in calls)
    assert all(call["task_type"] == "retrieval_document" for call in calls)
    assert all(call["output_dimensionality"] == 768 for call in calls)


def test_embed_query_uses_gemini_retrieval_query_embedding(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr(chroma_service, "_configured_api_key", None)
    monkeypatch.setattr(chroma_service.genai, "configure", lambda **_: None)
    monkeypatch.setattr(
        chroma_service.genai,
        "embed_content",
        lambda **kwargs: {"embedding": [1, 2]}
        if kwargs["output_dimensionality"] == 768
        else pytest.fail("Expected 768-dimensional embeddings."),
    )

    embedding = chroma_service.embed_query("question")

    assert embedding == [1.0, 2.0]
    assert all(type(value) is float for value in embedding)


def test_embedding_requires_gemini_api_key(monkeypatch: Any) -> None:
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        chroma_service.embed_query("question")
