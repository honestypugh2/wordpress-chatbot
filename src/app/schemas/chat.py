"""Request/response models for the chat API.

These define the contract the WordPress widget (via APIM) relies on. Keep them
stable and free of internal implementation detail.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Role(StrEnum):
    user = "user"
    assistant = "assistant"
    system = "system"


class ChatMessage(BaseModel):
    """A single turn in the conversation."""

    role: Role
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    """Inbound chat request from the WordPress widget."""

    message: str = Field(
        min_length=1,
        max_length=8000,
        description="The resident's current question.",
    )
    session_id: str | None = Field(
        default=None,
        max_length=128,
        description="Opaque client session id for continuity. Not used for auth.",
    )
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="Prior turns for context; server trims to a safe maximum.",
    )
    locale: str = Field(default="en-US", max_length=10)
    page_url: str | None = Field(
        default=None,
        max_length=2048,
        description="The county page the resident is on (for context only).",
    )


class Citation(BaseModel):
    """A grounding source surfaced to the user for transparency."""

    doc_id: str
    title: str
    category: str
    snippet: str
    url: str | None = None
    score: float = 0.0


class ChatResponse(BaseModel):
    """Outbound chat response to the widget."""

    answer: str
    citations: list[Citation] = Field(default_factory=list)
    session_id: str
    correlation_id: str
    route: str = Field(description="Which agent path handled the turn.")
    mode: str = Field(description="'foundry' or 'local-fallback'.")
    disclaimer: str = (
        "AI-generated using synthetic, fictional county data. Verify important "
        "details with the relevant department. Not legal, financial, medical, or "
        "emergency advice. For emergencies call 911."
    )
