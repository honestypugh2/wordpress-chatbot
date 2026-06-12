"""Orchestrator — routes a turn through the agent graph.

Flow (a working routed path, extensible to richer multi-agent behavior):

    1. SafetyAgent      → may short-circuit (emergency / blocked / too long)
    2. WorkflowAgent    → may short-circuit (actionable intent, e.g. report a pothole)
    3. Retrieval / grounding, by configured pattern:
         * local         → RetrievalAgent grounds on the local county KB
         * azure_search  → Foundry AI Search tool (prompt agent); custom retriever opt-in
         * bing          → BingGroundingAgent answers directly (web citations)
         * hybrid        → Foundry AI Search tool first; if it has no grounded
                           answer, fall back to Bing Custom Search grounding
    4. CitizenAssistant → composes the grounded answer (Foundry or local fallback)

This mirrors how a Microsoft Agent Framework workflow or a Foundry prompt agent
with tools would be composed, while remaining fully runnable offline.
"""

from __future__ import annotations

import uuid
from functools import lru_cache

from app.agents.ai_search_grounding import AzureAISearchGroundingAgent
from app.agents.base import AgentContext
from app.agents.bing_grounding import BingGroundingAgent
from app.agents.citizen_assistant import CitizenAssistantAgent
from app.agents.foundry_client import get_foundry_client
from app.agents.retrieval_agent import RetrievalAgent
from app.agents.safety_agent import SafetyAgent
from app.agents.workflow_agent import WorkflowAgent
from app.config import RetrievalPattern, Settings, get_settings
from app.core.correlation import get_correlation_id
from app.core.logging import get_logger
from app.schemas.chat import ChatRequest, ChatResponse, Citation

logger = get_logger("app.orchestrator")


class Orchestrator:
    """Coordinates the agent graph for a chat turn."""

    def __init__(self) -> None:
        self.safety = SafetyAgent()
        self.workflow = WorkflowAgent()
        self.retrieval = RetrievalAgent()
        self.bing = BingGroundingAgent()
        self.ai_search = AzureAISearchGroundingAgent()
        self.citizen = CitizenAssistantAgent()

    async def handle(self, request: ChatRequest) -> ChatResponse:
        settings = get_settings()
        session_id = request.session_id or uuid.uuid4().hex
        correlation_id = get_correlation_id()

        ctx = AgentContext(
            message=request.message,
            session_id=session_id,
            correlation_id=correlation_id,
            locale=request.locale,
            page_url=request.page_url,
            history=request.history[-settings.chat_history_max_turns :],
        )

        # 1. Safety guardrails.
        safety = await self.safety.run(ctx)
        if safety.handled:
            return self._respond(ctx, safety.output, safety.route, citations=[])

        # 2. Actionable workflow intents.
        workflow = await self.workflow.run(ctx)
        if workflow.handled:
            return self._respond(ctx, workflow.output, workflow.route, citations=[])

        pattern = settings.effective_retrieval_pattern

        # 3a. Bing-only grounding answers directly with web citations.
        if pattern is RetrievalPattern.bing:
            bing = await self.bing.run(ctx)
            if bing.handled:
                return self._respond(
                    ctx, bing.output, bing.route, citations=self._grounding_citations(ctx)
                )
            # Grounding unavailable — fall through to local RAG as a safety net.

        # 3a2. Azure AI Search via the Foundry AI Search tool. This is the primary
        # grounding for Pattern 2 (azure_search) AND Pattern 3 (hybrid): when the
        # cloud is configured we ground on the Azure AI Search index through the
        # `county-assistant-ai-search` prompt agent rather than the in-repo
        # retriever. The custom retriever is opt-in via AZURE_SEARCH_USE_CUSTOM_RETRIEVER.
        use_ai_search_tool = (
            pattern in (RetrievalPattern.azure_search, RetrievalPattern.hybrid)
            and not settings.azure_search_use_custom_retriever
        )
        if use_ai_search_tool:
            ais = await self.ai_search.run(ctx)
            # An AI Search answer only counts as a real hit when it is actually
            # grounded (i.e. it returned citations). A polite "I couldn't find
            # that in the documents" reply carries NO citations — in hybrid that
            # is exactly the signal to fall back to Bing Custom Search.
            grounded = ais.handled and bool(ctx.metadata.get("citations"))

            if pattern is RetrievalPattern.hybrid:
                if grounded:
                    return self._respond(
                        ctx, ais.output, ais.route, citations=self._grounding_citations(ctx)
                    )
                # AI Search could not answer from the index — clear its partial
                # state and fall back to Grounding with Bing Custom Search.
                logger.info("hybrid_fallback_to_bing", extra={"reason": ais.route})
                self._clear_grounding(ctx)
                bing = await self.bing.run(ctx)
                if bing.handled:
                    return self._respond(
                        ctx,
                        bing.output,
                        bing.route,
                        citations=self._grounding_citations(ctx),
                    )
                # Bing unavailable too — fall through to the local safety net.
                self._clear_grounding(ctx)
            elif ais.handled:
                # Pattern 2 (azure_search): return the agent's answer as-is.
                return self._respond(
                    ctx, ais.output, ais.route, citations=self._grounding_citations(ctx)
                )
            # Else fall through to the custom retriever / local index (safety net).

        # 3b. Retrieval (grounding) for local, the opt-in custom retriever, and the
        # offline safety net when the cloud grounding paths above were unavailable.
        await self.retrieval.run(ctx)

        # 3c. Hybrid with the opt-in custom retriever: when KB results are weak,
        # fall back to Bing grounding (the AI Search tool path above handles its
        # own Bing fallback, so this only applies to the custom-retriever path).
        if (
            pattern is RetrievalPattern.hybrid
            and settings.azure_search_use_custom_retriever
            and self._needs_fallback(ctx, settings)
        ):
            bing = await self.bing.run(ctx)
            if bing.handled:
                return self._respond(
                    ctx, bing.output, bing.route, citations=self._grounding_citations(ctx)
                )

        # 4. Answer composition.
        answer = await self.citizen.run(ctx)
        return self._respond(
            ctx,
            answer.output,
            answer.route,
            citations=self._citations(ctx),
        )

    @staticmethod
    def _needs_fallback(ctx: AgentContext, settings: Settings) -> bool:
        """True when KB retrieval is too sparse/weak to answer (hybrid pattern)."""
        if len(ctx.retrieved) < settings.hybrid_min_results:
            return True
        top = max((rc.score for rc in ctx.retrieved), default=0.0)
        return top < settings.hybrid_min_score

    @staticmethod
    def _clear_grounding(ctx: AgentContext) -> None:
        """Drop partial grounding state so a failed path can't leak its mode/citations."""
        ctx.metadata.pop("mode", None)
        ctx.metadata.pop("citations", None)

    @staticmethod
    def _grounding_citations(ctx: AgentContext) -> list[Citation]:
        """Citations produced by a grounding prompt agent (web or search sources)."""
        citations = ctx.metadata.get("citations", [])
        return list(citations) if citations else []

    def _citations(self, ctx: AgentContext) -> list[Citation]:
        seen: set[str] = set()
        citations: list[Citation] = []
        for rc in ctx.retrieved:
            if rc.chunk.doc_id in seen:
                continue
            seen.add(rc.chunk.doc_id)
            snippet = rc.chunk.text.strip()
            snippet = snippet[:200] + ("…" if len(snippet) > 200 else "")
            citations.append(
                Citation(
                    doc_id=rc.chunk.doc_id,
                    title=rc.chunk.title,
                    category=rc.chunk.category,
                    snippet=snippet,
                    url=rc.chunk.url,
                    score=rc.score,
                )
            )
        return citations

    def _respond(
        self,
        ctx: AgentContext,
        answer: str,
        route: str,
        *,
        citations: list[Citation],
    ) -> ChatResponse:
        mode = ctx.metadata.get("mode") or (
            "foundry" if get_foundry_client().available else "local-fallback"
        )
        logger.info("turn_complete", extra={"route": route, "mode": mode})
        return ChatResponse(
            answer=answer,
            citations=citations,
            session_id=ctx.session_id,
            correlation_id=ctx.correlation_id,
            route=route,
            mode=mode,
        )


@lru_cache(maxsize=1)
def get_orchestrator() -> Orchestrator:
    """Return a cached orchestrator instance."""
    return Orchestrator()
