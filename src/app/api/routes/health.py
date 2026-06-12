"""Health and readiness routes.

These endpoints are intentionally cheap and dependency-free so that load
balancers, APIM probes, and AWS/WordPress health checks can call them safely.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
def health() -> HealthResponse:
    """Liveness probe — confirms the process is up."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="county-assistant",
        version=__version__,
        environment=settings.app_env,
    )


@router.get("/ready", response_model=HealthResponse, summary="Readiness check")
def ready() -> HealthResponse:
    """Readiness probe.

    PLACEHOLDER: the next implementation pass should verify downstream
    dependencies here (Foundry project endpoint reachability, RAG index, etc.).
    """
    settings = get_settings()
    return HealthResponse(
        status="ready",
        service="county-assistant",
        version=__version__,
        environment=settings.app_env,
    )
