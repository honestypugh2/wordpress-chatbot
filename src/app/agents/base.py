"""Shared agent abstractions.

Clean, minimal interfaces so agents compose and can later be promoted to
Foundry prompt agents or Agent Framework workflows without churn.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from app.rag.models import RetrievedChunk
from app.schemas.chat import ChatMessage


@dataclass
class AgentContext:
    """Per-turn context threaded through the agent graph."""

    message: str
    session_id: str
    correlation_id: str
    locale: str = "en-US"
    page_url: str | None = None
    history: list[ChatMessage] = field(default_factory=list)
    # Working memory populated as agents run.
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Outcome of an agent step."""

    output: str = ""
    handled: bool = False
    route: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class BaseAgent(abc.ABC):
    """Base class for all agents."""

    name: str = "agent"

    @abc.abstractmethod
    async def run(self, ctx: AgentContext) -> AgentResult:
        """Execute this agent against the context."""
        raise NotImplementedError
