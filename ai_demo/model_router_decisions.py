"""
Demonstrates how to inspect Model Router decisions and build
a simple routing audit log for FinOps visibility.
"""

import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

load_dotenv()

# ── Client setup ─────────────────────────────────────────────────────────
# Exclude the environment credential so blank AZURE_CLIENT_ID/SECRET/TENANT_ID
# values in .env don't trigger service-principal auth — fall back to az login.
project = AIProjectClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(exclude_environment_credential=True),
)
openai_client = project.get_openai_client()


def call_with_routing_audit(query: str, complexity_tag: str = "auto") -> dict:
    """Returns routing metadata for FinOps logging.

    complexity_tag is only a label recorded in the audit record. The Model Router
    chooses the underlying model automatically from the prompt content.
    """
    system_prompt = "You are a Custom Technology technical assistant."

    response = openai_client.responses.create(
        model=os.environ["MODEL_ROUTER_DEPLOYMENT"],
        input=query,
        instructions=system_prompt,
    )

    usage = response.usage
    routing_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_routed_to": response.model,
        "input_tokens": usage.input_tokens if usage else None,
        "output_tokens": usage.output_tokens if usage else None,
        "total_tokens": usage.total_tokens if usage else None,
        "complexity_tag": complexity_tag,
        "query_preview": query[:80],
        "cost_tier": "low" if "mini" in response.model else "high",
    }

    # In production: emit to Application Insights or Azure Monitor custom metrics
    print(json.dumps(routing_record, indent=2))
    return routing_record


if __name__ == "__main__":
    # A trivial query — the Router picks a low-cost model (gpt-4.1-mini).
    print("=== Simple query (auto) ===")
    call_with_routing_audit(
        "What does the acronym PIC stand for?",
    )

    # A complex query — the Router picks a stronger model (gpt-4.1).
    print("\n=== Complex query (high) ===")
    call_with_routing_audit(
        "Compare the PIC32MZ and PIC32MX families across CPU architecture, "
        "peripheral set, and power management, and recommend one for a "
        "battery-powered industrial sensor.",
        complexity_tag="high",
    )