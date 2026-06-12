"""Application errors and FastAPI exception handlers.

We translate internal exceptions into a stable, PII-free JSON error contract that
the WordPress widget can render safely. The correlation id is always returned so
support can trace an issue end to end.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.correlation import get_correlation_id
from app.core.logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger("app.errors")


class AppError(Exception):
    """Base application error with an HTTP status and safe public message."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str = "An unexpected error occurred.") -> None:
        super().__init__(message)
        self.message = message


class RetrievalError(AppError):
    status_code = 502
    code = "retrieval_error"


class AgentError(AppError):
    status_code = 502
    code = "agent_error"


class SafetyRejection(AppError):
    """Raised when input/output is blocked by safety/validation."""

    # 422 (Unprocessable Content). Use the literal for cross-version Starlette
    # compatibility, since the named constant was renamed in newer releases.
    status_code = 422
    code = "safety_rejected"


def _error_body(code: str, message: str, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "correlation_id": get_correlation_id() or None,
        }
    }
    if extra:
        body["error"].update(extra)
    return body


def register_exception_handlers(app: FastAPI) -> None:
    """Attach JSON exception handlers to the app.

    FastAPI is imported lazily here so the shared ``app.core`` package can be
    imported by the Azure Functions host without a web framework installed.
    """
    from fastapi import Request, status
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        logger.warning("app_error", extra={"code": exc.code, "detail": str(exc)})
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        logger.info("validation_error", extra={"errors": exc.errors()})
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body(
                "validation_error",
                "The request was invalid. Please check your input and try again.",
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Never leak internal details to a public county website.
        logger.exception("unhandled_error", extra={"detail": str(exc)})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body(
                "internal_error",
                "The assistant is temporarily unavailable. Please try again shortly.",
            ),
        )
