"""
Per-User Cost Attribution Demo — Identity + AI Gateway (APIM) pattern.

This shows the *client half* of per-user chargeback/showback:

    user identity  ->  APIM AI Gateway  ->  Foundry model
         |                  |                    |
    x-user-id /        captures identity     returns token
    Entra JWT          + token usage         usage per request
                       (emit-token-metric +
                        log to Log Analytics)

The APIM policy (apim/per-user-cost-attribution.policy.xml) is the *gateway half*:
it captures the caller identity (Entra ID claim / subscription / custom header),
emits a per-user token metric, and logs a structured record to Log Analytics. APIM
is the trustworthy place to do this because it sees both the request identity and
the model's token usage, and the caller cannot tamper with the emitted record.

This client demonstrates:
  1. Passing user identity to the gateway (custom header and/or Entra bearer token).
  2. Reading token usage per request (from the model response).
  3. Building a per-user cost record for chargeback/showback.
  4. (Optional) Shipping that record to Azure Monitor / Log Analytics via the
     Logs Ingestion API — gated behind env vars so the demo runs without it.
"""

import json
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

# ── Pricing table (USD per 1M tokens) — adjust to current Azure pricing ──────
# Keyed by a substring match on the model the Router actually selected.
PRICE_PER_1M = {
    "mini": 0.40,
    "grok": 0.50,
    "gpt-5": 2.50,
    "o3": 2.00,
}
DEFAULT_PRICE_PER_1M = 2.00


def _price_for(model: str) -> float:
    for key, price in PRICE_PER_1M.items():
        if key in model:
            return price
    return DEFAULT_PRICE_PER_1M


def _make_client(user_id: str, entra_token: str | None) -> AzureOpenAI:
    """Build an AzureOpenAI client pointed at the APIM gateway, carrying identity.

    Identity is attached two ways (the gateway policy can use either):
      * x-user-id    — custom header for app-managed user ids (simplest).
      * Authorization — Entra ID bearer token for end-to-end SSO attribution.
    """
    headers = {
        # Per-user attribution header — APIM policy reads this for the cost record.
        "x-user-id": user_id,
        # Team/department attribution for roll-ups (optional).
        "x-team-id": os.environ.get("TEAM_ID", "unassigned"),
    }
    if entra_token:
        # When present, the gateway validates the JWT and prefers its 'oid' claim
        # over the x-user-id header (stronger, tamper-proof identity).
        headers["Authorization"] = f"Bearer {entra_token}"

    return AzureOpenAI(
        azure_endpoint=os.environ["APIM_ENDPOINT"],
        api_key=os.environ["APIM_SUBSCRIPTION_KEY"],
        api_version="2025-04-01-preview",
        default_headers=headers,
    )


def call_for_user(
    user_id: str,
    user_query: str,
    deployment: str = "model-router",
    entra_token: str | None = None,
) -> dict:
    """Call the model on behalf of a user and return a per-user cost record."""
    client = _make_client(user_id, entra_token)
    request_id = str(uuid.uuid4())

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": "You are a Custom Technology technical support assistant."},
            {"role": "user", "content": user_query},
        ],
        max_tokens=1000,
        # Surfaces in the response and APIM logs; ties client + gateway records.
        user=user_id,
    )

    usage = response.usage
    model_used = response.model
    total_tokens = usage.total_tokens if usage else 0
    est_cost = (total_tokens / 1_000_000) * _price_for(model_used)

    # Per-user cost record — the unit of chargeback/showback. APIM emits an
    # authoritative copy; this client-side copy is useful for local dashboards
    # and for correlating by request_id.
    record = {
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "team_id": os.environ.get("TEAM_ID", "unassigned"),
        "model_routed_to": model_used,
        "prompt_tokens": usage.prompt_tokens if usage else None,
        "completion_tokens": usage.completion_tokens if usage else None,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(est_cost, 6),
        "query_preview": user_query[:80],
    }

    print(json.dumps(record, indent=2))
    _maybe_emit_to_log_analytics(record)
    return record


def _maybe_emit_to_log_analytics(record: dict) -> None:
    """Optionally ship the record to Log Analytics via the Logs Ingestion API.

    Gated behind env vars so the demo runs without monitoring wired up. In
    production the *gateway* (APIM) is the primary emitter; this client path is
    for app-side telemetry or environments without an AI-gateway tier.

    Required env vars to enable:
      LOGS_DCR_ENDPOINT   — Data Collection Endpoint logs ingestion URI
      LOGS_DCR_IMMUTABLE_ID — Data Collection Rule immutable id (dcr-...)
      LOGS_DCR_STREAM     — custom stream name (e.g. Custom-AIUsage_CL)
    Auth: DefaultAzureCredential (needs 'Monitoring Metrics Publisher' on the DCR).
    """
    endpoint = os.environ.get("LOGS_DCR_ENDPOINT")
    rule_id = os.environ.get("LOGS_DCR_IMMUTABLE_ID")
    stream = os.environ.get("LOGS_DCR_STREAM")
    if not (endpoint and rule_id and stream):
        print("  [log-analytics] skipped (LOGS_DCR_* env vars not set)")
        return

    try:
        from azure.identity import DefaultAzureCredential
        from azure.monitor.ingestion import LogsIngestionClient  # type: ignore[import-not-found]
    except ImportError:
        print("  [log-analytics] skipped (uv add azure-monitor-ingestion azure-identity)")
        return

    client = LogsIngestionClient(
        endpoint=endpoint,
        credential=DefaultAzureCredential(exclude_environment_credential=True),
    )
    client.upload(rule_id=rule_id, stream_name=stream, logs=[record])
    print(f"  [log-analytics] uploaded record {record['request_id']} to {stream}")


if __name__ == "__main__":
    # Two different users hitting the same gateway — each gets its own cost record.
    print("=== User: alice@county.gov ===")
    call_for_user(
        user_id="alice@county.gov",
        user_query="What is the difference between PIC32MZ and PIC32MX product families?",
    )

    print("\n=== User: bob@county.gov ===")
    call_for_user(
        user_id="bob@county.gov",
        user_query="What is the maximum operating voltage for the PIC32MX270F256B?",
    )
