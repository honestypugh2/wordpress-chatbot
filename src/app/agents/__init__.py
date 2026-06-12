"""Agent layer.

Implements a small, clean multi-agent structure:

    Orchestrator
      ├── SafetyAgent      (input/output validation, guardrails)
      ├── RetrievalAgent   (RAG over the synthetic county KB)
      ├── CitizenAssistant (answer composition; Foundry or local fallback)
      └── WorkflowAgent    (stub: routes actionable intents, e.g. "report a pothole")

Pattern: **Hybrid** — Azure AI Foundry (azure-ai-projects ~= 2.2.0) is the system of
record for the model/agent; Microsoft Agent Framework concepts inspire the local
orchestration so the prototype runs without cloud access and lifts cleanly into
Foundry prompt agents later. See docs/architecture-overview.md.
"""

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.agents.orchestrator import Orchestrator, get_orchestrator

__all__ = [
    "AgentContext",
    "AgentResult",
    "BaseAgent",
    "Orchestrator",
    "get_orchestrator",
]
