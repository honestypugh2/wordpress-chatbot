"""Retrieval agent — grounds the turn on the synthetic county KB."""

from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.core.errors import RetrievalError
from app.core.logging import get_logger
from app.rag import get_retriever

logger = get_logger("app.agents.retrieval")


class RetrievalAgent(BaseAgent):
    """Populate `ctx.retrieved` with relevant KB chunks."""

    name = "retrieval"

    async def run(self, ctx: AgentContext) -> AgentResult:
        try:
            retriever = get_retriever()
            results = retriever.search(ctx.message)
        except Exception as exc:  # noqa: BLE001
            logger.warning("retrieval_failed", extra={"detail": str(exc)})
            raise RetrievalError("Knowledge base retrieval failed.") from exc

        ctx.retrieved = results
        logger.info(
            "retrieval_done",
            extra={"hits": len(results), "top_score": results[0].score if results else 0.0},
        )
        return AgentResult(
            handled=False,
            route="retrieval",
            data={"hits": len(results)},
        )
