"""Safety / validation agent (guardrail stub).

A defense-in-depth check that runs before answering. The prototype implements
lightweight, transparent rules; production should layer Azure AI Content Safety
and prompt-shield at both the APIM gateway and here.

TODO(prod): integrate Azure AI Content Safety (text moderation + prompt shields)
and jurisdiction-specific policy. Keep this as the single choke point for outbound
answer validation too.
"""

from __future__ import annotations

import re

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.agents.safety")

# Intents that should be redirected to authoritative human channels.
_EMERGENCY_RE = re.compile(
    r"\b(911|emergency|suicide|overdose|active shooter|gun|bomb|kill myself)\b",
    re.IGNORECASE,
)
_BLOCK_RE = re.compile(
    r"\b(ignore (all|previous) instructions|system prompt|jailbreak)\b",
    re.IGNORECASE,
)

EMERGENCY_RESPONSE = (
    "If this is an emergency, please call 911 immediately. For non-emergency "
    "crisis support you can also dial 988 (Suicide & Crisis Lifeline). I can help "
    "with general information about county services, but I can't assist with "
    "emergencies."
)


class SafetyAgent(BaseAgent):
    """Input validation and guardrails."""

    name = "safety"

    async def run(self, ctx: AgentContext) -> AgentResult:
        settings = get_settings()
        text = ctx.message.strip()

        if len(text) > settings.chat_max_input_chars:
            return AgentResult(
                handled=True,
                route="safety:too-long",
                output=(
                    "Your message is a bit long for me to process. Please shorten "
                    "it and try again."
                ),
            )

        if _EMERGENCY_RE.search(text):
            logger.info("safety_emergency_redirect")
            return AgentResult(
                handled=True,
                route="safety:emergency",
                output=EMERGENCY_RESPONSE,
            )

        if _BLOCK_RE.search(text):
            logger.info("safety_prompt_injection_blocked")
            return AgentResult(
                handled=True,
                route="safety:blocked",
                output=(
                    "I can only help with questions about county services and "
                    "information. How can I help you with a county service today?"
                ),
            )

        # Passed all checks; let the orchestrator continue.
        return AgentResult(handled=False, route="safety:pass")
