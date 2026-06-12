"""Application settings loaded from environment / .env.

Uses pydantic-settings so configuration is typed, validated, and `.env`-driven.
No secrets are hard-coded; in shared environments prefer managed identity and
Key Vault over plaintext values.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RetrievalPattern(StrEnum):
    """Selectable knowledge-grounding strategy (set via RETRIEVAL_PATTERN).

    * ``local``        — in-memory index over the synthetic KB (offline demos).
    * ``azure_search`` — Azure AI Search RAG over ingested WordPress content.
    * ``bing``         — Grounding with Bing Custom Search via a Foundry prompt
                         agent (no local index; the agent answers with web
                         citations scoped to allowed domains).
    * ``hybrid``       — Azure AI Search first; fall back to Bing Custom Search
                         grounding when the index has no / weak coverage.
    """

    local = "local"
    azure_search = "azure_search"
    bing = "bing"
    hybrid = "hybrid"


class DemoSite(StrEnum):
    """Which WordPress demo front-end the assistant is presented on.

    * ``westvale`` — our synthetic *County of Westvale* WordPress site (default).
    * ``staging``  — a generic *customer staging* WordPress site. Grounded ONLY
                     via Bing Custom Search over its public domains (no scraping
                     or ingestion). The real staging domain is supplied at
                     runtime via ``BING_ALLOWED_DOMAINS`` / the Bing Custom Search
                     instance config — never hard-coded here.
    """

    westvale = "westvale"
    staging = "staging"


class Settings(BaseSettings):
    """Strongly-typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    app_env: str = Field(default="local", description="local | dev | prod")
    app_name: str = Field(default="county-assistant")
    app_log_level: str = Field(default="INFO")
    app_log_json: bool = Field(
        default=False,
        description="Emit structured JSON logs (recommended for prod / log pipelines).",
    )
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    app_cors_origins: str = Field(
        default="http://localhost",
        description="Comma-separated list of allowed CORS origins (WordPress site origins).",
    )

    # --- Azure AI Foundry (azure-ai-projects ~= 2.2.0) ---
    azure_ai_project_endpoint: str = Field(default="")
    # Account-level endpoint for the OpenAI-compatible client (chat + embeddings).
    # Optional: when blank it is derived from azure_ai_project_endpoint. The
    # azure-ai-projects 2.2.0 project client does not serve the embeddings route,
    # so we target the account endpoint directly via AzureOpenAI.
    azure_ai_account_endpoint: str = Field(default="")
    azure_ai_model_deployment: str = Field(default="gpt-4o-mini")
    azure_ai_agent_id: str = Field(default="")
    azure_openai_api_version: str = Field(default="2024-10-21")
    # When false (or Foundry not configured), the orchestrator runs in a local,
    # grounded fallback mode so the prototype is runnable without cloud access.
    foundry_enabled: bool = Field(default=False)

    # --- Retrieval pattern selection ---
    # Switch the grounding strategy without code changes. See RetrievalPattern.
    retrieval_pattern: RetrievalPattern = Field(
        default=RetrievalPattern.local,
        description="local | azure_search | bing | hybrid",
    )
    # Which WordPress demo site the assistant is presented on.
    demo_site_profile: DemoSite = Field(
        default=DemoSite.westvale,
        description="westvale (synthetic) | staging (customer staging site)",
    )

    # --- Grounding with Bing Custom Search (Foundry "prompt agent" tool) ---
    # The supported path is a Foundry prompt agent created with the
    # ``BingCustomSearchPreviewTool`` (preview) and invoked through the OpenAI
    # Responses API. Provide an existing agent name, or a connection (name or id)
    # + instance name so the backend can create the agent on first use.
    bing_grounding_enabled: bool = Field(default=False)
    bing_grounding_agent_name: str = Field(
        default="",
        description="Name of an existing Foundry prompt agent with the Bing grounding tool.",
    )
    bing_connection_name: str = Field(
        default="",
        description="Foundry connection name for the Bing Custom Search resource (resolved to id).",
    )
    bing_connection_id: str = Field(
        default="",
        description="Foundry connection id for the Bing Custom Search resource (used directly).",
    )
    bing_custom_search_instance_name: str = Field(
        default="",
        description="Bing Custom Search configuration/instance name scoping allowed domains.",
    )
    bing_allowed_domains: str = Field(
        default="",
        description="Comma-separated public domains the Bing instance is scoped to (override).",
    )
    # Hybrid fallback thresholds: trigger Bing when Azure AI Search returns fewer
    # than N hits or the best score is below the floor. The score is the semantic
    # reranker score (0-4 scale); on the county KB, genuine topic hits rerank
    # ~2.8+ while off-topic/missing content tops out around ~1.3-1.7, so a 2.0
    # floor routes "missing content" queries to the Bing Custom Search fallback.
    hybrid_min_results: int = Field(default=1)
    hybrid_min_score: float = Field(default=2.0)

    # --- Retrieval / RAG ---
    azure_search_endpoint: str = Field(default="")
    azure_search_index: str = Field(default="county-kb")
    # Leave the API key blank to authenticate with managed identity / Azure CLI
    # via DefaultAzureCredential (recommended). A key is only used if provided.
    azure_search_api_key: str = Field(default="")
    azure_search_semantic_config: str = Field(
        default="",
        description="Optional semantic-ranker configuration name on the index.",
    )
    # --- Azure AI Search grounding via a Foundry prompt agent (Pattern 2 default) ---
    # By default the ``azure_search`` pattern grounds via the Foundry AI Search
    # tool (a prompt agent invoked through the Responses API). Set
    # ``AZURE_SEARCH_USE_CUSTOM_RETRIEVER=true`` to instead demo the in-repo custom
    # retriever (LocalRetriever / AzureAISearchRetriever + chat completions).
    azure_search_use_custom_retriever: bool = Field(default=False)
    azure_search_connection_name: str = Field(
        default="",
        description="Foundry connection name for Azure AI Search (resolved to id).",
    )
    azure_search_connection_id: str = Field(
        default="",
        description="Foundry connection id for Azure AI Search (used directly).",
    )
    azure_search_agent_name: str = Field(
        default="",
        description="Name of an existing Foundry prompt agent with the AI Search tool.",
    )
    azure_search_query_type: str = Field(
        default="vector_semantic_hybrid",
        description="AI Search tool query type: simple|vector|semantic|*_hybrid.",
    )
    # --- Embeddings (vector / hybrid retrieval) ---
    # Embeddings are generated through the Foundry project's Azure OpenAI client,
    # so they reuse azure_ai_project_endpoint. Set rag_vector_enabled to run a
    # hybrid (keyword + vector) query at retrieval time.
    azure_embedding_deployment: str = Field(default="text-embedding-3-small")
    azure_embedding_dimensions: int = Field(default=1536)
    rag_vector_enabled: bool = Field(
        default=False,
        description="Enable hybrid keyword+vector retrieval (requires embeddings).",
    )
    # Path to the synthetic county knowledge base used by the local retriever.
    rag_kb_path: str = Field(default="data/county_kb")
    rag_top_k: int = Field(default=4)
    rag_chunk_size: int = Field(default=900)
    rag_chunk_overlap: int = Field(default=150)

    # --- APIM (AI Gateway) ---
    apim_gateway_url: str = Field(default="")
    apim_subscription_key: str = Field(default="")
    # APIM AI-gateway in FRONT of the Azure OpenAI model (token limits, token
    # metrics, semantic caching, managed-identity backend auth). When both are
    # set, the chat-completions and embeddings clients route through APIM instead
    # of calling Foundry directly. Leave blank to call Foundry directly (the
    # default), so local / offline runs and direct-Foundry deploys keep working.
    #   * azure_openai_gateway_endpoint -> APIM host that serves the /openai route,
    #     e.g. https://<apim>.azure-api.net (the client appends /openai/...).
    #   * azure_openai_gateway_key      -> APIM subscription key for the AOAI API
    #     (sent as the api-key header).
    azure_openai_gateway_endpoint: str = Field(default="")
    azure_openai_gateway_key: str = Field(default="")

    # --- Observability (OpenTelemetry) ---
    otel_enabled: bool = Field(default=False)
    otel_service_name: str = Field(default="county-assistant")
    otel_exporter_otlp_endpoint: str = Field(default="")
    applicationinsights_connection_string: str = Field(default="")

    # --- Chat guardrails ---
    chat_max_input_chars: int = Field(default=4000)
    chat_history_max_turns: int = Field(default=12)

    @property
    def cors_origins(self) -> list[str]:
        """Parsed list of allowed CORS origins."""
        return [o.strip() for o in self.app_cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "prod"

    @property
    def foundry_ready(self) -> bool:
        """True only when Foundry is enabled AND minimally configured."""
        return self.foundry_enabled and bool(self.azure_ai_project_endpoint)

    @property
    def search_ready(self) -> bool:
        """True when an Azure AI Search endpoint is configured.

        Authentication falls back to managed identity / DefaultAzureCredential
        when no API key is supplied.
        """
        return bool(self.azure_search_endpoint)

    @property
    def embeddings_ready(self) -> bool:
        """True when an embedding deployment is reachable via the Foundry project."""
        return bool(self.account_endpoint) and bool(self.azure_embedding_deployment)

    @property
    def model_gateway_ready(self) -> bool:
        """True when an APIM AI-gateway fronts the Azure OpenAI model.

        When set, chat-completions and embeddings clients route through APIM
        (token limits, token metrics, semantic caching, managed-identity backend
        auth) instead of calling Foundry directly.
        """
        return bool(self.azure_openai_gateway_endpoint) and bool(
            self.azure_openai_gateway_key
        )

    @property
    def account_endpoint(self) -> str:
        """Account-level endpoint for the OpenAI-compatible client.

        Prefers an explicit ``azure_ai_account_endpoint``; otherwise derives it
        from ``azure_ai_project_endpoint`` by stripping the ``/api/projects/...``
        suffix (e.g. ``https://<acct>.services.ai.azure.com``).
        """
        if self.azure_ai_account_endpoint:
            return self.azure_ai_account_endpoint.rstrip("/")
        endpoint = self.azure_ai_project_endpoint
        if not endpoint:
            return ""
        marker = "/api/projects/"
        base = endpoint.split(marker, 1)[0] if marker in endpoint else endpoint
        return base.rstrip("/")

    @property
    def openai_endpoint(self) -> str:
        """Azure OpenAI resource URL (``https://<acct>.openai.azure.com``).

        Used by the Azure AI Search ``AzureOpenAIVectorizer`` for query-time
        embedding. Derived from :attr:`account_endpoint` by swapping the
        ``.services.ai.azure.com`` / ``.cognitiveservices.azure.com`` host suffix
        for ``.openai.azure.com``.
        """
        base = self.account_endpoint
        if not base:
            return ""
        for suffix in (".services.ai.azure.com", ".cognitiveservices.azure.com"):
            if suffix in base:
                return base.replace(suffix, ".openai.azure.com")
        return base

    @property
    def bing_grounding_ready(self) -> bool:
        """True when Bing Custom Search grounding can be attempted.

        Requires Foundry (for the prompt agent) plus either a pre-created agent
        name, or a connection (name or id) to create one on first use.
        """
        if not (self.bing_grounding_enabled and self.foundry_ready):
            return False
        return bool(
            self.bing_grounding_agent_name
            or self.bing_connection_name
            or self.bing_connection_id
        )

    @property
    def ai_search_grounding_ready(self) -> bool:
        """True when the Foundry AI Search tool (prompt agent) can be attempted.

        Requires Foundry plus either a pre-created agent name, or a project
        connection (name or id) to the Azure AI Search service.
        """
        if not self.foundry_ready:
            return False
        return bool(
            self.azure_search_agent_name
            or self.azure_search_connection_name
            or self.azure_search_connection_id
        )

    @property
    def azure_search_ready(self) -> bool:
        """True when the ``azure_search`` pattern can run.

        Default path uses the Foundry AI Search tool (needs a connection/agent).
        The opt-in custom-retriever path needs a Search endpoint instead.
        """
        if self.azure_search_use_custom_retriever:
            return self.search_ready
        return self.ai_search_grounding_ready or self.search_ready

    @property
    def effective_retrieval_pattern(self) -> RetrievalPattern:
        """Resolve the requested pattern against what is actually configured.

        Degrades gracefully so the prototype always runs:
          * ``azure_search`` without a Search endpoint or AI Search tool -> ``local``
          * ``hybrid`` without a Search endpoint                         -> ``local``
          * ``bing`` without Bing grounding configured                  -> ``local``
          * ``hybrid`` keeps Search even if Bing is unavailable (fallback no-ops).
        """
        pattern = self.retrieval_pattern
        if pattern is RetrievalPattern.bing and not self.bing_grounding_ready:
            return RetrievalPattern.local
        if pattern is RetrievalPattern.azure_search and not self.azure_search_ready:
            return RetrievalPattern.local
        if pattern is RetrievalPattern.hybrid and not self.search_ready:
            return RetrievalPattern.local
        return pattern


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
