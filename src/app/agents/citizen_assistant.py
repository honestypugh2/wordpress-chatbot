"""Citizen assistant agent — composes the grounded answer.

Uses Azure AI Foundry when available; otherwise composes a deterministic,
citation-grounded answer from retrieved chunks so the prototype is fully runnable
offline. Either way the answer is grounded in the synthetic county KB.
"""

from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.agents.foundry_client import get_foundry_client
from app.agents.site_profiles import get_site_profile
from app.core.logging import get_logger

logger = get_logger("app.agents.citizen")

_NO_CONTEXT = (
    "I don't have specific information about that in the county knowledge base yet. "
    "For the most accurate help, please contact the relevant county department or "
    "visit the county services page. Is there another county service I can help with?"
)


def _build_context_block(ctx: AgentContext) -> str:
    parts: list[str] = []
    for i, rc in enumerate(ctx.retrieved, start=1):
        parts.append(
            f"[Source {i}] Title: {rc.chunk.title} (category: {rc.chunk.category})\n"
            f"{rc.chunk.text}"
        )
    return "\n\n".join(parts)


def _local_compose(ctx: AgentContext) -> str:
    """Deterministic, grounded answer used when Foundry is unavailable."""
    if not ctx.retrieved:
        return _NO_CONTEXT

    top = ctx.retrieved[0].chunk
    # Surface the most relevant passage, trimmed, with a clear grounding note.
    snippet = top.text.strip()
    if len(snippet) > 700:
        snippet = snippet[:700].rsplit(" ", 1)[0] + "…"

    titles = ", ".join(
        sorted({rc.chunk.title for rc in ctx.retrieved})
    )
    return (
        f"Here's what I found about your question, based on the county's "
        f"information on **{top.title}**:\n\n{snippet}\n\n"
        f"(Sources: {titles}.) If you need more detail, contact the relevant "
        f"department listed on the county services page."
    )


class CitizenAssistantAgent(BaseAgent):
    """Compose the final answer for the resident."""

    name = "citizen_assistant"

    async def run(self, ctx: AgentContext) -> AgentResult:
        context_block = _build_context_block(ctx)
        foundry = get_foundry_client()
        system_prompt = get_site_profile().system_prompt

        if foundry.available and context_block:
            user_prompt = (
                f"Resident question: {ctx.message}\n\n"
                f"Context from the county knowledge base:\n{context_block}\n\n"
                "Answer using only this context and cite the source titles you used."
            )
            answer = await foundry.generate(system_prompt, user_prompt)
            if answer:
                ctx.metadata["mode"] = "foundry"
                return AgentResult(handled=True, route="citizen:foundry", output=answer)
            logger.info("foundry_returned_empty_falling_back")

        ctx.metadata["mode"] = "local-fallback"
        return AgentResult(
            handled=True,
            route="citizen:local",
            output=_local_compose(ctx),
        )
