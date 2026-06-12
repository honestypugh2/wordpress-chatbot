"""FastAPI application entrypoint.

Wires the experience-layer-facing API that the WordPress widget calls (via APIM).
Keep this module thin: routing, middleware, lifecycle, observability.

This architecture separates the experience layer from the intelligence layer:
WordPress on AWS remains the front door, while Azure AI Foundry becomes the brain.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import chat, health, site
from app.config import get_settings
from app.core import CorrelationIdMiddleware, configure_logging, register_exception_handlers
from app.core.logging import get_logger
from app.core.telemetry import configure_telemetry

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Warm up retrieval index and agents on startup."""
    settings = get_settings()
    # Eagerly build the retriever and orchestrator so the first request is fast
    # and any configuration problems surface at startup.
    from app.agents import get_orchestrator
    from app.rag import get_retriever

    retriever = get_retriever()
    get_orchestrator()
    logger.info(
        "startup_complete",
        extra={
            "env": settings.app_env,
            "foundry_ready": settings.foundry_ready,
            "kb_chunks": retriever.chunk_count,
        },
    )
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    """Application factory."""
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title="County Assistant API",
        version=__version__,
        summary="Azure AI Foundry chatbot backend for an AWS-hosted WordPress county site.",
        lifespan=lifespan,
    )

    # Correlation id first so it's available to everything downstream.
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*", "X-Correlation-Id"],
        expose_headers=["X-Correlation-Id"],
    )

    register_exception_handlers(app)
    configure_telemetry(app)

    app.include_router(health.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(site.router, prefix="/api")

    @app.get("/", tags=["meta"], summary="Service banner")
    def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "health": "/api/health",
            "chat": "/api/chat",
        }

    return app


app = create_app()
