"""Correlation-ID propagation.

A correlation id ties together every hop of a request — WordPress widget -> APIM
-> backend -> Foundry agent -> retrieval. We read an inbound header (set by APIM)
or mint a new id, store it in a context variable so loggers can attach it
automatically, and echo it back on the response.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, MutableMapping

CORRELATION_HEADER = "X-Correlation-Id"

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def new_correlation_id() -> str:
    """Mint a new correlation id."""
    return uuid.uuid4().hex


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> str:
    """Return the current correlation id (may be empty outside a request)."""
    return _correlation_id.get()


class CorrelationIdMiddleware:
    """Pure-ASGI middleware: ensure every request has a correlation id and echo it.

    Implemented without importing Starlette/FastAPI so the shared ``app.core``
    package stays host-agnostic — the Azure Functions host imports the identical
    orchestrator without pulling in a web framework. It still plugs into FastAPI
    via ``app.add_middleware(CorrelationIdMiddleware)``.
    """

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: Callable[[], Awaitable[Any]],
        send: Callable[[Any], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        incoming = headers.get(CORRELATION_HEADER.lower().encode(), b"").decode() or (
            new_correlation_id()
        )
        set_correlation_id(incoming)

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.append(
                    (CORRELATION_HEADER.encode(), incoming.encode())
                )
                message["headers"] = response_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
