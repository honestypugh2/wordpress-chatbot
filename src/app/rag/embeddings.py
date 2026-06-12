"""Embedding client for vector / hybrid retrieval.

Generates text embeddings through the Azure AI Foundry project's OpenAI-compatible
client (same pattern as `FoundryClient`), so it reuses `azure_ai_project_endpoint`
and managed-identity auth. All imports are soft so the prototype runs without the
SDK or credentials — callers receive `None`/empty results and fall back to keyword
retrieval.

The vector field name and profile produced by `scripts/index_kb_to_search.py`:
  - field:   ``content_vector`` (Collection(Edm.Single))
  - profile: HNSW (cosine)
"""

from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger("app.rag.embeddings")

VECTOR_FIELD = "content_vector"


class EmbeddingClient:
    """Thin wrapper over an Azure OpenAI embeddings deployment."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: object | None = None
        self._available = False
        if self._settings.embeddings_ready:
            self._available = self._try_init()

    @property
    def available(self) -> bool:
        """True when an embeddings deployment is configured and reachable."""
        return self._available

    @property
    def dimensions(self) -> int:
        return self._settings.azure_embedding_dimensions

    def _try_init(self) -> bool:
        try:
            from azure.identity import (
                DefaultAzureCredential,
                get_bearer_token_provider,
            )
            from openai import AzureOpenAI
        except ImportError:
            logger.warning("embeddings_sdk_unavailable")
            return False

        try:
            # Preferred path: route embeddings through the APIM AI-gateway
            # (managed-identity backend auth, shared token governance). The
            # gateway exposes the standard /openai route and accepts the APIM
            # subscription key via the api-key header. Falls back to a direct
            # Entra-auth call to the Foundry account endpoint.
            if self._settings.model_gateway_ready:
                self._client = AzureOpenAI(
                    azure_endpoint=self._settings.azure_openai_gateway_endpoint.rstrip(
                        "/"
                    ),
                    api_key=self._settings.azure_openai_gateway_key,
                    api_version=self._settings.azure_openai_api_version,
                )
                logger.info(
                    "embeddings_initialized",
                    extra={
                        "deployment": self._settings.azure_embedding_deployment,
                        "transport": "apim_gateway",
                    },
                )
                return True

            # Bind to the account endpoint with Entra auth (the project client's
            # /openai/v1 route does not serve the embeddings deployment).
            token_provider = get_bearer_token_provider(
                DefaultAzureCredential(),
                "https://cognitiveservices.azure.com/.default",
            )
            self._client = AzureOpenAI(
                azure_endpoint=self._settings.account_endpoint,
                azure_ad_token_provider=token_provider,
                api_version=self._settings.azure_openai_api_version,
            )
            logger.info(
                "embeddings_initialized",
                extra={
                    "deployment": self._settings.azure_embedding_deployment,
                    "transport": "direct",
                },
            )
            return True
        except Exception as exc:  # noqa: BLE001 - never crash the prototype
            logger.warning("embeddings_init_failed", extra={"detail": str(exc)})
            return False

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns [] if embeddings are unavailable."""
        if not self._available or self._client is None or not texts:
            return []
        try:
            response = self._client.embeddings.create(  # type: ignore[attr-defined]
                model=self._settings.azure_embedding_deployment,
                input=texts,
                dimensions=self._settings.azure_embedding_dimensions,
            )
            return [list(item.embedding) for item in response.data]
        except Exception as exc:  # noqa: BLE001
            logger.warning("embeddings_batch_failed", extra={"detail": str(exc)})
            return []

    def embed_query(self, text: str) -> list[float] | None:
        """Embed a single query. Returns None if embeddings are unavailable."""
        vectors = self.embed([text])
        return vectors[0] if vectors else None


@lru_cache(maxsize=1)
def get_embedding_client() -> EmbeddingClient:
    """Return a cached embedding client."""
    return EmbeddingClient()
