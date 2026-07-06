"""Seed the FinOps lookup tables used by the per-user cost dashboard.

Uploads pricing, per-user budgets, and a user directory into the custom Log
Analytics tables provisioned by ``infra/modules/finops.bicep``:

    PRICING_CL          (Model, InputTokensPrice, OutputTokensPrice)
    USER_QUOTA_CL       (UserId, CostQuota)
    USER_DIRECTORY_CL   (UserId, DisplayName, Upn)

Rows are sent through the Logs Ingestion API (Data Collection Endpoint + Rule),
so this is idempotent in the sense that re-running appends new rows; the
dashboard queries take ``arg_max(TimeGenerated, *)`` per key, so the latest
upload wins.

Authentication:
    ``DefaultAzureCredential`` (Azure CLI / managed identity). The identity needs
    the *Monitoring Metrics Publisher* role on the Data Collection Rule — granted
    by the Bicep module to the workload identity and, optionally, to the
    developer/CI principal passed as ``searchIndexAdminPrincipalId``.

Configuration (from ``az deployment group ... --query properties.outputs`` or .env):
    LOGS_DCR_ENDPOINT             finopsLogsIngestionEndpoint
    LOGS_DCR_IMMUTABLE_ID         finopsDcrImmutableId
    LOGS_PRICING_STREAM           finopsPricingStream        (default Custom-PRICING_CL)
    LOGS_USER_QUOTA_STREAM        finopsUserQuotaStream      (default Custom-USER_QUOTA_CL)
    LOGS_USER_DIRECTORY_STREAM    finopsUserDirectoryStream  (default Custom-USER_DIRECTORY_CL)

Usage:
    # uv add azure-monitor-ingestion azure-identity   (or: uv sync --extra finops)
    export LOGS_DCR_ENDPOINT="https://<dce>.<region>.ingest.monitor.azure.com"
    export LOGS_DCR_IMMUTABLE_ID="dcr-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    uv run python scripts/seed_finops_tables.py

    # Custom data files / only one table:
    uv run python scripts/seed_finops_tables.py --pricing data/finops/pricing.json --skip-quota --skip-directory
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "finops"
DEFAULT_STREAMS = {
    "pricing": "Custom-PRICING_CL",
    "user_quota": "Custom-USER_QUOTA_CL",
    "user_directory": "Custom-USER_DIRECTORY_CL",
}


def _load_rows(path: Path) -> list[dict]:
    """Read a JSON array of records and stamp each with TimeGenerated (UTC)."""
    if not path.exists():
        raise FileNotFoundError(f"Seed file not found: {path}")
    rows = json.loads(path.read_text())
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a JSON array of objects.")
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        row.setdefault("TimeGenerated", now)
    return rows


def _upload(client: object, rule_id: str, stream: str, rows: list[dict], label: str) -> None:
    if not rows:
        print(f"  [{label}] no rows — skipped")
        return
    client.upload(rule_id=rule_id, stream_name=stream, logs=rows)  # type: ignore[attr-defined]
    print(f"  [{label}] uploaded {len(rows)} row(s) to {stream}")


def _drop_blank_sp_env() -> None:
    """Remove blank AZURE_* service-principal placeholders so DefaultAzureCredential
    skips EnvironmentCredential and falls through to Azure CLI / managed identity.

    A repo .env may define AZURE_CLIENT_ID/AZURE_TENANT_ID/AZURE_CLIENT_SECRET as
    empty placeholders (e.g. ``""``). Once load_dotenv() puts those in os.environ,
    EnvironmentCredential treats them as a (broken) service principal and raises.
    """
    for key in ("AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_CLIENT_SECRET"):
        value = os.environ.get(key, "").strip().strip("\"'")
        if not value:
            os.environ.pop(key, None)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    _drop_blank_sp_env()
    parser = argparse.ArgumentParser(description="Seed FinOps lookup tables via the Logs Ingestion API.")
    parser.add_argument("--pricing", type=Path, default=DEFAULT_DATA_DIR / "pricing.json")
    parser.add_argument("--user-quota", type=Path, default=DEFAULT_DATA_DIR / "user_quota.json")
    parser.add_argument("--user-directory", type=Path, default=DEFAULT_DATA_DIR / "user_directory.json")
    parser.add_argument("--skip-pricing", action="store_true")
    parser.add_argument("--skip-quota", action="store_true")
    parser.add_argument("--skip-directory", action="store_true")
    args = parser.parse_args(argv)

    endpoint = os.environ.get("LOGS_DCR_ENDPOINT")
    rule_id = os.environ.get("LOGS_DCR_IMMUTABLE_ID")
    if not (endpoint and rule_id):
        print(
            "ERROR: set LOGS_DCR_ENDPOINT and LOGS_DCR_IMMUTABLE_ID "
            "(from the finopsLogsIngestionEndpoint / finopsDcrImmutableId deployment outputs).",
            file=sys.stderr,
        )
        return 2

    pricing_stream = os.environ.get("LOGS_PRICING_STREAM", DEFAULT_STREAMS["pricing"])
    quota_stream = os.environ.get("LOGS_USER_QUOTA_STREAM", DEFAULT_STREAMS["user_quota"])
    directory_stream = os.environ.get("LOGS_USER_DIRECTORY_STREAM", DEFAULT_STREAMS["user_directory"])

    try:
        from azure.identity import DefaultAzureCredential
        from azure.monitor.ingestion import LogsIngestionClient  # type: ignore[import-not-found]
    except ImportError:
        print(
            "ERROR: missing dependencies. Run: uv add azure-monitor-ingestion azure-identity "
            "(or uv sync --extra finops).",
            file=sys.stderr,
        )
        return 2

    client = LogsIngestionClient(endpoint=endpoint, credential=DefaultAzureCredential())

    print(f"Seeding FinOps tables via {endpoint}")
    if not args.skip_pricing:
        _upload(client, rule_id, pricing_stream, _load_rows(args.pricing), "pricing")
    if not args.skip_quota:
        _upload(client, rule_id, quota_stream, _load_rows(args.user_quota), "user-quota")
    if not args.skip_directory:
        _upload(client, rule_id, directory_stream, _load_rows(args.user_directory), "user-directory")
    print("Done. Allow ~1-3 min for rows to appear in Log Analytics.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
