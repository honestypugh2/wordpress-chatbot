"""Grounding with Bing Custom Search via a Foundry prompt agent.

The Bing Search / Bing Custom Search REST APIs were retired (August 2025). The
supported path is the **Grounding with Bing Custom Search** tool (preview)
attached to a Foundry *prompt agent*. The agent is created with the
``azure-ai-projects`` SDK (``create_version`` + ``PromptAgentDefinition`` +
``BingCustomSearchPreviewTool``) and invoked through the OpenAI **Responses
API** (``project.get_openai_client().responses.create(...)`` with an
``agent_reference``). The tool runs server-side and returns an answer plus URL
citations scoped to the domains configured in the Bing Custom Search instance
(for the demo: the county's public website pages).

Design:
  * All Azure SDK access is soft-imported and wrapped, so the prototype still runs
    offline. When Bing grounding is not configured/reachable, callers receive
    ``None`` and the orchestrator degrades (to local, or — for the hybrid pattern
    — keeps the Azure AI Search answer).
  * Either reference a pre-provisioned agent (``BING_GROUNDING_AGENT_NAME``) or
    create one from a connection (name or id) + Bing custom search instance name.

Note: the Bing grounding tool requires normal outbound network access and does
not work behind a VPN or private endpoint. Per the Bing tool terms, both the
website URLs and the Bing query URLs from the citation annotations are surfaced.

See ``docs/retrieval-patterns.md`` for provisioning details and test queries.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from functools import lru_cache

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.agents.site_profiles import get_site_profile
from app.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.text import strip_citation_markers
from app.schemas.chat import Citation

logger = get_logger("app.agents.bing_grounding")


@dataclass
class BingGroundingResult:
    """A grounded answer produced by the Bing Custom Search agent."""

    answer: str
    citations: list[Citation] = field(default_factory=list)


class BingGroundingClient:
    """Thin wrapper over a Foundry agent configured with Bing Custom Search."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._project: object | None = None
        self._openai: object | None = None
        self._agent_name: str = self._settings.bing_grounding_agent_name
        self._available = False
        if self._settings.bing_grounding_ready:
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
                "bing_grounding_sdk_unavailable",
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
                "bing_grounding_initialized",
                extra={"agent": self._agent_name or "(created on demand)"},
            )
            return True
        except Exception as exc:  # noqa: BLE001 - prototype must not crash
            logger.warning("bing_grounding_init_failed", extra={"detail": str(exc)})
            return False

    def ground(self, query: str, *, instructions: str | None = None) -> BingGroundingResult | None:
        """Run the Bing Custom Search grounding agent for ``query``.

        Returns ``None`` when grounding is unavailable or fails, so callers can
        fall back. The prompt agent executes the Bing tool server-side; we read
        the Responses API output text and map URL citation annotations to
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
                extra_body={
                    "agent_reference": {"name": agent_name, "type": "agent_reference"}
                },
            )
            return self._read_result(response)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            logger.warning("bing_grounding_failed", extra={"detail": str(exc)})
            return None

    def _ensure_agent(self, instructions: str | None) -> str:
        """Create a prompt agent with the Bing Custom Search tool, if possible.

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
                BingCustomSearchConfiguration,
                BingCustomSearchPreviewTool,
                BingCustomSearchToolParameters,
                PromptAgentDefinition,
            )
        except ImportError:
            logger.warning("bing_custom_search_tool_unavailable")
            return ""
        try:
            tool = BingCustomSearchPreviewTool(
                bing_custom_search_preview=BingCustomSearchToolParameters(
                    search_configurations=[
                        BingCustomSearchConfiguration(
                            project_connection_id=conn_id,
                            instance_name=self._settings.bing_custom_search_instance_name,
                        )
                    ]
                )
            )
            agent = self._project.agents.create_version(  # type: ignore[attr-defined]
                agent_name="county-assistant-bing-grounding",
                definition=PromptAgentDefinition(
                    model=self._settings.azure_ai_model_deployment,
                    instructions=instructions or "Answer using grounded web citations only.",
                    tools=[tool],
                ),
            )
            self._agent_name = str(agent.name)
            return self._agent_name
        except Exception as exc:  # noqa: BLE001
            logger.warning("bing_grounding_agent_create_failed", extra={"detail": str(exc)})
            return ""

    def _resolve_connection_id(self) -> str:
        """Resolve the Bing connection id from an explicit id or connection name."""
        if self._settings.bing_connection_id:
            return self._settings.bing_connection_id
        name = self._settings.bing_connection_name
        if not name or self._project is None:
            return ""
        try:
            connection = self._project.connections.get(name)  # type: ignore[attr-defined]
            return str(connection.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("bing_connection_lookup_failed", extra={"detail": str(exc)})
            return ""

    def _read_result(self, response: object) -> BingGroundingResult | None:
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
                            category="web",
                            snippet="",
                            url=url,
                            score=0.0,
                        )
                    )
        if not answer:
            return None
        return BingGroundingResult(answer=answer, citations=citations)


@lru_cache(maxsize=1)
def get_bing_grounding_client() -> BingGroundingClient:
    """Return a cached Bing Custom Search grounding client."""
    return BingGroundingClient()


class BingGroundingAgent(BaseAgent):
    """Agent wrapper that grounds an answer via Bing Custom Search.

    Returns ``handled=True`` only when the prompt agent produced a grounded
    answer, so the orchestrator can fall back (to local, or to the Azure AI
    Search answer in the hybrid pattern) when grounding is unavailable.
    """

    name = "bing_grounding"

    def __init__(self, client: BingGroundingClient | None = None) -> None:
        self._client = client or get_bing_grounding_client()

    async def run(self, ctx: AgentContext) -> AgentResult:
        if not self._client.available:
            return AgentResult(handled=False, route="bing:unavailable")

        profile = get_site_profile()
        result = await asyncio.to_thread(
            self._client.ground, ctx.message, instructions=profile.system_prompt
        )
        if result is None or not result.answer:
            return AgentResult(handled=False, route="bing:no-result")

        ctx.metadata["mode"] = "bing-grounding"
        ctx.metadata["citations"] = result.citations
        return AgentResult(
            output=result.answer,
            handled=True,
            route="citizen:bing",
            data={"citations": result.citations},
        )
