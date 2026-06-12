"""Retrieval service.

Defines the `Retriever` protocol the agent layer depends on, plus two
implementations:

* `LocalRetriever` — an in-memory index over the synthetic county knowledge base
  (no cloud required), used for demos and offline development.
* `AzureAISearchRetriever` — a production retriever backed by Azure AI Search,
  authenticated with managed identity (preferred) or an API key.

`get_retriever()` selects Azure AI Search automatically when an endpoint is
configured, and gracefully falls back to the local index otherwise. Both satisfy
the same `Retriever` protocol, so the agent layer never changes.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Protocol, runtime_checkable

from app.config import RetrievalPattern, Settings, get_settings
from app.core.logging import get_logger
from app.rag.chunking import chunk_document, load_documents
from app.rag.embeddings import VECTOR_FIELD, EmbeddingClient, get_embedding_client
from app.rag.indexer import InMemoryIndex
from app.rag.models import Chunk, RetrievedChunk

logger = get_logger("app.rag")


@runtime_checkable
class Retriever(Protocol):
    """Retrieval interface used by the agent layer."""

    @property
    def chunk_count(self) -> int: ...

    def search(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]: ...


class LocalRetriever:
    """Local, in-memory retriever over the synthetic KB (no cloud required)."""

    def __init__(self) -> None:
        settings = get_settings()
        self._top_k = settings.rag_top_k
        self._index = InMemoryIndex()
        docs = load_documents(settings.rag_kb_path)
        for doc in docs:
            self._index.add(
                chunk_document(
                    doc,
                    chunk_size=settings.rag_chunk_size,
                    overlap=settings.rag_chunk_overlap,
                )
            )
        self._index.finalize()
        logger.info(
            "rag_index_built",
            extra={"documents": len(docs), "chunks": self._index.size},
        )

    @property
    def chunk_count(self) -> int:
        return self._index.size

    def search(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        return self._index.search(query, top_k or self._top_k)


class AzureAISearchRetriever:
    """Retriever backed by Azure AI Search.

    Authentication prefers managed identity via `DefaultAzureCredential`; an API
    key is used only when explicitly configured. The expected index schema is
    produced by `scripts/index_kb_to_search.py` and uses these fields:
    `chunk_id`, `doc_id`, `title`, `category`, `content`, `url`, and (for hybrid
    retrieval) `content_vector`.

    Retrieval mode is chosen automatically:
      * keyword + semantic ranking (always), and
      * vector (kNN) when `rag_vector_enabled` is set and embeddings are reachable,
        which combines into a hybrid query.
    """

    # Field names in the Azure AI Search index (kept in one place).
    _F_CHUNK_ID = "chunk_id"
    _F_DOC_ID = "doc_id"
    _F_TITLE = "title"
    _F_CATEGORY = "category"
    _F_CONTENT = "content"
    _F_URL = "url"

    def __init__(
        self,
        client: Any,
        settings: Settings,
        embedder: EmbeddingClient | None = None,
    ) -> None:
        self._client = client
        self._top_k = settings.rag_top_k
        self._semantic_config = settings.azure_search_semantic_config or None
        self._index_name = settings.azure_search_index
        self._embedder = embedder
        self._vector_enabled = bool(
            settings.rag_vector_enabled and embedder is not None and embedder.available
        )

    @classmethod
    def create(cls, settings: Settings) -> AzureAISearchRetriever | None:
        """Build a retriever, or return None if the SDK/credentials are unavailable."""
        client = _build_search_client(settings)
        if client is None:
            return None
        embedder = get_embedding_client() if settings.rag_vector_enabled else None
        return cls(client, settings, embedder)

    @property
    def chunk_count(self) -> int:
        """Document count reported by the search service (-1 if unavailable)."""
        try:
            return int(self._client.get_document_count())
        except Exception as exc:  # noqa: BLE001 - count is informational only
            logger.warning("search_document_count_failed", extra={"detail": str(exc)})
            return -1

    def search(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        k = top_k or self._top_k
        kwargs: dict[str, Any] = {"search_text": query, "top": k}
        if self._semantic_config:
            kwargs["query_type"] = "semantic"
            kwargs["semantic_configuration_name"] = self._semantic_config

        vector_query = self._build_vector_query(query, k)
        if vector_query is not None:
            kwargs["vector_queries"] = [vector_query]

        results: list[RetrievedChunk] = []
        for item in self._client.search(**kwargs):
            chunk = Chunk(
                chunk_id=str(item.get(self._F_CHUNK_ID, "")),
                doc_id=str(item.get(self._F_DOC_ID, "")),
                title=str(item.get(self._F_TITLE, "")),
                category=str(item.get(self._F_CATEGORY, "general")),
                text=str(item.get(self._F_CONTENT, "")),
                url=item.get(self._F_URL) or None,
            )
            # Reranker score (semantic) is preferred when present, else BM25 score.
            score = item.get("@search.reranker_score") or item.get("@search.score") or 0.0
            results.append(RetrievedChunk(chunk=chunk, score=round(float(score), 4)))
        logger.info(
            "search_query_complete",
            extra={"hits": len(results), "hybrid": vector_query is not None},
        )
        return results

    def _build_vector_query(self, query: str, k: int) -> Any | None:
        """Build a kNN vector query, or None if vectors are disabled/unavailable."""
        if not self._vector_enabled or self._embedder is None:
            return None
        try:
            from azure.search.documents.models import VectorizedQuery
        except ImportError:
            return None
        vector = self._embedder.embed_query(query)
        if not vector:
            return None
        return VectorizedQuery(
            vector=vector,
            k_nearest_neighbors=k,
            fields=VECTOR_FIELD,
        )


def _build_search_client(settings: Settings) -> Any | None:
    """Construct an Azure AI Search client, or None if unavailable.

    Uses soft imports so the prototype runs without the optional `[rag]` extra.
    """
    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient
    except ImportError:
        logger.warning("azure_search_sdk_missing")
        return None

    try:
        credential: Any
        if settings.azure_search_api_key:
            credential = AzureKeyCredential(settings.azure_search_api_key)
        else:
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
        return SearchClient(
            endpoint=settings.azure_search_endpoint,
            index_name=settings.azure_search_index,
            credential=credential,
        )
    except Exception as exc:  # noqa: BLE001 - never crash the prototype on auth/setup
        logger.warning("azure_search_client_init_failed", extra={"detail": str(exc)})
        return None


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    """Return a cached retriever for the active retrieval pattern.

    The chunk-based retriever backs the ``local`` and ``hybrid`` patterns, plus
    the opt-in ``azure_search`` custom-retriever path. By default the
    ``azure_search`` pattern grounds via the Foundry AI Search tool (a prompt
    agent), which does not use a chunk retriever; a ``LocalRetriever`` is returned
    as a harmless default in that case.
    """
    settings = get_settings()
    pattern = settings.effective_retrieval_pattern
    if pattern in (RetrievalPattern.azure_search, RetrievalPattern.hybrid):
        retriever = AzureAISearchRetriever.create(settings)
        if retriever is not None:
            logger.info(
                "retriever_selected",
                extra={"backend": "azure-ai-search", "pattern": str(pattern)},
            )
            return retriever
        logger.warning("azure_search_unavailable_fallback_local")
    logger.info(
        "retriever_selected",
        extra={"backend": "local", "pattern": str(pattern)},
    )
    return LocalRetriever()

