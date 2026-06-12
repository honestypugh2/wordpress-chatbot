"""Azure AI Search grounding via a Foundry prompt agent (Pattern 2 default).

The ``azure_search`` retrieval pattern grounds answers on an Azure AI Search
index using the **Foundry AI Search tool** attached to a *prompt agent*. The
agent is created with the ``azure-ai-projects`` SDK (``create_version`` +
``PromptAgentDefinition`` + ``AzureAISearchTool``) and invoked through the OpenAI
**Responses API** (``project.get_openai_client().responses.create(...)`` with an
``agent_reference``). The tool runs the retrieval server-side and returns an
answer plus URL citation annotations.

This is the default for Pattern 2. The in-repo custom retriever
(``LocalRetriever`` / ``AzureAISearchRetriever`` + chat completions) remains
available for demos and offline runs, gated behind
``AZURE_SEARCH_USE_CUSTOM_RETRIEVER=true``.

Design:
  * All Azure SDK access is soft-imported and wrapped, so the prototype still runs
    offline. When the tool is not configured/reachable, callers receive ``None``
    and the orchestrator degrades to the custom retriever / local index.
  * Either reference a pre-provisioned agent (``AZURE_SEARCH_AGENT_NAME``) or
    create one from a project connection (name or id) + index name.

See ``docs/retrieval-patterns.md`` for provisioning details and test queries.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.agents.site_profiles import get_site_profile
from app.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.text import strip_citation_markers
from app.schemas.chat import Citation

logger = get_logger("app.agents.ai_search_grounding")


@dataclass
class AISearchGroundingResult:
    """A grounded answer produced by the Azure AI Search prompt agent."""

    answer: str
    citations: list[Citation] = field(default_factory=list)


class AzureAISearchGroundingClient:
    """Thin wrapper over a Foundry prompt agent configured with the AI Search tool."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._project: object | None = None
        self._openai: object | None = None
        self._agent_name: str = self._settings.azure_search_agent_name
        self._available = False
        if self._settings.ai_search_grounding_ready:
            self._available = self._try_init()

    @property
    def available(self) -> bool:
        """True when the Foundry project + OpenAI clients initialised successfully."""
        return self._available

    def _try_init(self) -> bool:
        try:
            from azure.ai.projects import AIProjectClient
            from azure.identity import DefaultAzureCredential
        except ImportError:
            logger.warning(
                "ai_search_grounding_sdk_unavailable",
                extra={"hint": "uv add azure-ai-projects azure-identity"},
            )
            return False

        try:
            self._project = AIProjectClient(
                endpoint=self._settings.azure_ai_project_endpoint,
                credential=DefaultAzureCredential(),
            )
            # The Responses API is reached through the project's OpenAI client.
            self._openai = self._project.get_openai_client()
            logger.info(
                "ai_search_grounding_initialized",
                extra={"agent": self._agent_name or "(created on demand)"},
            )
            return True
        except Exception as exc:  # noqa: BLE001 - prototype must not crash
            logger.warning("ai_search_grounding_init_failed", extra={"detail": str(exc)})
            return False

    def ground(
        self, query: str, *, instructions: str | None = None
    ) -> AISearchGroundingResult | None:
        """Run the Azure AI Search prompt agent for ``query``.

        Returns ``None`` when grounding is unavailable or fails, so callers can
        fall back. The prompt agent executes the AI Search tool server-side; we
        read the Responses API output text and map URL citation annotations to
        ``Citation``s.
        """
        if not self._available or self._openai is None:
            return None
        try:
            agent_name = self._agent_name or self._ensure_agent(instructions)
            if not agent_name:
                return None
            response = self._openai.responses.create(  # type: ignore[attr-defined]
                input=query,
                tool_choice="required",
                extra_body={
                    "agent_reference": {"name": agent_name, "type": "agent_reference"}
                },
            )
            return self._read_result(response)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            logger.warning("ai_search_grounding_failed", extra={"detail": str(exc)})
            return None

    def _ensure_agent(self, instructions: str | None) -> str:
        """Create a prompt agent with the Azure AI Search tool, if possible.

        Returns the agent *name* (referenced by the Responses API) or ``""`` when
        no connection is configured / creation fails.
        """
        if self._project is None:
            return ""
        conn_id = self._resolve_connection_id()
        if not conn_id:
            return ""
        try:
            from azure.ai.projects.models import (
                AISearchIndexResource,
                AzureAISearchQueryType,
                AzureAISearchTool,
                AzureAISearchToolResource,
                PromptAgentDefinition,
            )
        except ImportError:
            logger.warning("ai_search_tool_unavailable")
            return ""
        try:
            query_type = self._query_type(AzureAISearchQueryType)
            tool = AzureAISearchTool(
                azure_ai_search=AzureAISearchToolResource(
                    indexes=[
                        AISearchIndexResource(
                            project_connection_id=conn_id,
                            index_name=self._settings.azure_search_index,
                            query_type=query_type,
                        )
                    ]
                )
            )
            agent = self._project.agents.create_version(  # type: ignore[attr-defined]
                agent_name="county-assistant-ai-search",
                definition=PromptAgentDefinition(
                    model=self._settings.azure_ai_model_deployment,
                    instructions=instructions or "Answer using indexed sources with citations.",
                    tools=[tool],
                ),
            )
            self._agent_name = str(agent.name)
            return self._agent_name
        except Exception as exc:  # noqa: BLE001
            logger.warning("ai_search_agent_create_failed", extra={"detail": str(exc)})
            return ""

    def _query_type(self, enum_cls: type) -> Any:
        """Map the configured query-type string to the SDK enum (default hybrid)."""
        name = self._settings.azure_search_query_type.upper()
        default = getattr(enum_cls, "VECTOR_SEMANTIC_HYBRID", None)
        return getattr(enum_cls, name, default)

    def _resolve_connection_id(self) -> str:
        """Resolve the AI Search connection id from an explicit id or connection name."""
        if self._settings.azure_search_connection_id:
            return self._settings.azure_search_connection_id
        name = self._settings.azure_search_connection_name
        if not name or self._project is None:
            return ""
        try:
            connection = self._project.connections.get(name)  # type: ignore[attr-defined]
            return str(connection.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ai_search_connection_lookup_failed", extra={"detail": str(exc)})
            return ""

    def _read_result(self, response: object) -> AISearchGroundingResult | None:
        """Extract the answer and URL citations from a Responses API result."""
        answer = strip_citation_markers(str(getattr(response, "output_text", "") or ""))
        citations: list[Citation] = []
        seen: set[str] = set()
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", "") != "message":
                continue
            for content in getattr(item, "content", []) or []:
                if getattr(content, "type", "") != "output_text":
                    continue
                for ann in getattr(content, "annotations", []) or []:
                    if getattr(ann, "type", "") != "url_citation":
                        continue
                    url = getattr(ann, "url", None)
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    citations.append(
                        Citation(
                            doc_id=url,
                            title=(getattr(ann, "title", "") or url),
                            category="search",
                            snippet="",
                            url=url,
                            score=0.0,
                        )
                    )
        if not answer:
            return None
        return AISearchGroundingResult(answer=answer, citations=citations)


@lru_cache(maxsize=1)
def get_ai_search_grounding_client() -> AzureAISearchGroundingClient:
    """Return a cached Azure AI Search grounding client."""
    return AzureAISearchGroundingClient()


class AzureAISearchGroundingAgent(BaseAgent):
    """Agent wrapper that grounds an answer via the Foundry AI Search tool.

    Returns ``handled=True`` only when the prompt agent produced a grounded
    answer, so the orchestrator can fall back to the custom retriever / local
    index when the tool is unavailable.
    """

    name = "ai_search_grounding"

    def __init__(self, client: AzureAISearchGroundingClient | None = None) -> None:
        self._client = client or get_ai_search_grounding_client()

    async def run(self, ctx: AgentContext) -> AgentResult:
        if not self._client.available:
            return AgentResult(handled=False, route="ai-search:unavailable")

        profile = get_site_profile()
        result = await asyncio.to_thread(
            self._client.ground, ctx.message, instructions=profile.system_prompt
        )
        if result is None or not result.answer:
            return AgentResult(handled=False, route="ai-search:no-result")

        ctx.metadata["mode"] = "ai-search-grounding"
        ctx.metadata["citations"] = result.citations
        return AgentResult(
            output=result.answer,
            handled=True,
            route="citizen:ai-search",
            data={"citations": result.citations},
        )
