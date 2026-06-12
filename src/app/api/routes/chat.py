"""Chat route — the endpoint the WordPress widget calls via APIM."""

from __future__ import annotations

from fastapi import APIRouter

from app.agents import get_orchestrator
from app.core.logging import get_logger
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])
logger = get_logger("app.api.chat")


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask the County Assistant a question",
)
async def chat(request: ChatRequest) -> ChatResponse:
    """Handle a single chat turn.

    The experience layer (WordPress widget) posts here through APIM. The
    orchestrator routes the turn through safety, workflow, retrieval, and the
    citizen-assistant agent, returning a grounded, cited answer.
    """
    logger.info("chat_request", extra={"chars": len(request.message)})
    orchestrator = get_orchestrator()
    return await orchestrator.handle(request)
