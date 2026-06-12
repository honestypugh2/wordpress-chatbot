"""Workflow / action agent (stub).

Detects *actionable* intents (e.g., "report a pothole", "pay my property tax") and
returns a structured next-step with the right destination. In production this agent
would call county systems of record (311, payment portal) via tools/connections —
ideally as Foundry server-side tools or Agent Framework function tools.

TODO(prod): replace the keyword router with model-based intent classification and
wire real tool calls (311 intake API, permit center, payment portal) behind
managed identity. Add human-in-the-loop confirmation before any state change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.core.logging import get_logger

logger = get_logger("app.agents.workflow")


@dataclass(frozen=True)
class ActionIntent:
    name: str
    pattern: re.Pattern[str]
    response: str


# Synthetic destinations — all fictional.
_INTENTS: tuple[ActionIntent, ...] = (
    ActionIntent(
        name="report_pothole",
        pattern=re.compile(r"\b(pothole|road (damage|maintenance)|street.*(repair|hole))\b", re.I),
        response=(
            "You can report a pothole or road-maintenance issue through the "
            "Westvale 311 portal. You'll receive a tracking number to follow its "
            "status. (Prototype: this would open a 311 intake form.)"
        ),
    ),
    ActionIntent(
        name="pay_property_tax",
        pattern=re.compile(r"\b(pay|payment).*(property )?tax|tax bill\b", re.I),
        response=(
            "You can pay your property tax online via eCheck (no fee) or card. "
            "Have your parcel number ready. (Prototype: this would link to the "
            "Westvale Tax Portal payment flow.)"
        ),
    ),
    ActionIntent(
        name="report_concern",
        pattern=re.compile(r"\b(report|complaint).*(graffiti|dumping|streetlight|code)\b", re.I),
        response=(
            "Non-emergency concerns like graffiti, illegal dumping, or streetlight "
            "outages can be reported on the Westvale 311 portal for tracking. "
            "(Prototype: this would open the appropriate 311 category.)"
        ),
    ),
)


class WorkflowAgent(BaseAgent):
    """Route actionable intents to the right next step."""

    name = "workflow"

    async def run(self, ctx: AgentContext) -> AgentResult:
        for intent in _INTENTS:
            if intent.pattern.search(ctx.message):
                logger.info("workflow_intent_matched", extra={"intent": intent.name})
                return AgentResult(
                    handled=True,
                    route=f"workflow:{intent.name}",
                    output=intent.response,
                    data={"intent": intent.name, "actionable": True},
                )
        return AgentResult(handled=False, route="workflow:none")
