"""Azure Functions host for the County Assistant backend (serverless option).

This is the *recommended / default* compute for the scenario: it scales to
zero between bursts of resident traffic and runs only the thin glue that bridges
the WordPress widget's single ``POST {message}`` to the agent/orchestrator and
back to ``{answer, citations}``.

It deliberately shares the **same** orchestration logic as the FastAPI host
(``app.agents.Orchestrator``) — only the hosting model differs. APIM can route to
either backend without any change to the widget or the WordPress plugin.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# The shared application package lives in ../src. Add it to the path so this
# serverless host imports the identical orchestrator the FastAPI host uses.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import azure.functions as func  # noqa: E402

from app.agents import get_orchestrator  # noqa: E402
from app.agents.site_profiles import (  # noqa: E402
    effective_allowed_domains,
    get_site_profile,
)
from app.config import get_settings  # noqa: E402
from app.core.correlation import new_correlation_id, set_correlation_id  # noqa: E402
from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.schemas.chat import ChatRequest  # noqa: E402

configure_logging()
logger = get_logger("app.function")

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    """Liveness probe mirroring the FastAPI ``/api/health`` contract."""
    return func.HttpResponse(
        json.dumps({"status": "ok", "host": "azure-functions"}),
        mimetype="application/json",
        status_code=200,
    )


@app.route(route="site", methods=["GET"])
def site(req: func.HttpRequest) -> func.HttpResponse:
    """Return the active demo-site profile — same contract as FastAPI ``/api/site``.

    Lets the WordPress widget self-configure its title and greeting on load so
    they follow ``DEMO_SITE_PROFILE`` without rebuilding the page.
    """
    settings = get_settings()
    profile = get_site_profile(settings)
    body = {
        "site": str(profile.key),
        "county_name": profile.county_name,
        "short_name": profile.short_name,
        "title": profile.title,
        "greeting": profile.greeting,
        "retrieval_pattern": str(settings.effective_retrieval_pattern),
        "allowed_domains": list(effective_allowed_domains(profile, settings)),
    }
    return func.HttpResponse(
        json.dumps(body),
        mimetype="application/json",
        status_code=200,
    )


@app.route(route="chat", methods=["POST"])
async def chat(req: func.HttpRequest) -> func.HttpResponse:
    """Handle a single chat turn — same contract as the FastAPI ``/api/chat``.

    The WordPress widget (via APIM) posts ``{message, session_id, page_url}`` and
    receives a grounded, cited ``ChatResponse``. The orchestration itself is the
    shared :class:`app.agents.Orchestrator`.
    """
    # Reuse the correlation id minted by APIM, or start a new trace.
    set_correlation_id(req.headers.get("X-Correlation-Id") or new_correlation_id())

    try:
        payload = req.get_json()
    except ValueError:
        return _error(400, "invalid_json", "Request body must be valid JSON.")

    try:
        chat_request = ChatRequest.model_validate(payload)
    except Exception:  # noqa: BLE001 — surface a clean 422 to the gateway
        return _error(422, "invalid_request", "Request did not match the chat schema.")

    logger.info("chat_request", extra={"chars": len(chat_request.message)})
    response = await get_orchestrator().handle(chat_request)

    return func.HttpResponse(
        response.model_dump_json(),
        mimetype="application/json",
        status_code=200,
        headers={"X-Correlation-Id": response.correlation_id},
    )


def _error(status: int, code: str, message: str) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"error": {"code": code, "message": message}}),
        mimetype="application/json",
        status_code=status,
    )
