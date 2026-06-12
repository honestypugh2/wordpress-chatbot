"""Logging configuration.

Supports human-readable logs for local development and structured JSON logs for
production pipelines (App Insights / OTEL collectors). The current correlation id
is injected into every record via a logging filter so traces are joinable across
the WordPress -> APIM -> backend -> Foundry path.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from app.config import get_settings
from app.core.correlation import get_correlation_id

_CONFIGURED = False


class _CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id() or "-"
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Include any structured extras passed via logger.<level>(..., extra={...}).
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload.setdefault(key, value)
        return json.dumps(payload, default=str)


_RESERVED = set(logging.makeLogRecord({}).__dict__) | {
    "correlation_id",
    "message",
    "asctime",
    "taskName",
}


def configure_logging() -> None:
    """Configure root logging once, based on settings."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_CorrelationFilter())

    if settings.app_log_json:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s [%(correlation_id)s] %(name)s: %(message)s"
            )
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.app_log_level.upper())
    # Quiet noisy access logs; correlation middleware covers request tracing.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger."""
    configure_logging()
    return logging.getLogger(name)
