"""
Custom AI Demo — Direct Microsoft Foundry call via azure-ai-projects 2.x.
Demonstrates Model Router transparency and token usage interpretation.
"""

import os
import random
import time

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from openai import APIConnectionError, APIStatusError, RateLimitError

load_dotenv()

# ── Client setup ─────────────────────────────────────────────────────────
# Endpoint: "https://<resource>.ai.azure.com/api/projects/<project>"
# DefaultAzureCredential: uses az login locally, Managed Identity in prod.
# Exclude the environment credential so blank AZURE_CLIENT_ID/SECRET/TENANT_ID
# values in .env don't trigger service-principal auth — fall back to az login.
project = AIProjectClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(exclude_environment_credential=True),
)
openai_client = project.get_openai_client()


def create_with_retry(max_retries: int = 4, base_delay: float = 1.0, **kwargs):
    """Call responses.create with exponential backoff + jitter on transient errors.

    Retries on 5xx server errors, rate limits, and connection errors. Other
    errors (e.g. 4xx) are raised immediately.
    """
    for attempt in range(max_retries + 1):
        try:
            return openai_client.responses.create(**kwargs)
        except (RateLimitError, APIConnectionError) as exc:
            detail = str(exc)
        except APIStatusError as exc:
            if exc.status_code < 500:
                raise
            detail = f"HTTP {exc.status_code}"
        if attempt == max_retries:
            raise RuntimeError(
                f"responses.create failed after {max_retries + 1} attempts ({detail})"
            )
        delay = base_delay * (2 ** attempt) + random.uniform(0, base_delay)
        print(f"  transient error ({detail}); retrying in {delay:.1f}s "
              f"[attempt {attempt + 1}/{max_retries}]")
        time.sleep(delay)
    raise RuntimeError("unreachable")


def call_model_router(user_query: str, complexity: str = "auto") -> None:
    """
    Call the Custom Model Router endpoint via azure-ai-projects 2.x.
    complexity: "auto" (router decides), "high" (forces o3 routing)
    """

    # System prompt signals complexity to the Model Router.
    # The {"route":"high-complexity"} tag triggers o3 routing when set.
    system_content = (
        "You are a Custom Technology technical support assistant. "
        "Answer questions about Custom products, datasheets, and design guidance."
    )
    if complexity == "high":
        system_content += ' {"route":"high-complexity"}'

    # Responses API (Agents v2) — single input string, no messages list needed
    response = create_with_retry(
        model=os.environ["MODEL_ROUTER_DEPLOYMENT"],
        input=user_query,
        instructions=system_content,
    )

    # ── Token usage interpretation ────────────────────────────────────────
    usage = response.usage
    model_used = response.model  # Model Router reveals which model was selected

    print(f"Model selected by Router: {model_used}")
    if usage is not None:
        print(f"Input tokens:      {usage.input_tokens:,}")
        print(f"Output tokens:     {usage.output_tokens:,}")
        print(f"Total tokens:      {usage.total_tokens:,}")

        # Approximate cost visibility (adjust rates per current Azure pricing)
        cost_per_1m = 0.40 if "mini" in model_used else 2.00
        est_cost = (usage.total_tokens / 1_000_000) * cost_per_1m
        print(f"Estimated cost:    ${est_cost:.6f}")
    else:
        print("Token usage not available in response.")
    print(f"\nResponse:\n{response.output_text}\n")
    print("-" * 60)


# ── Example 1: Simple support query (routes to GPT-4.1 mini) ──────────────
print("=== Query 1: Simple Support (expect GPT-4.1 mini routing) ===")
call_model_router(
    "What is the maximum operating voltage for the PIC32MX270F256B microcontroller?"
)

# ── Example 2: Complex design query (routes to GPT-4.1) ───────────────────
print("=== Query 2: Complex Design (expect GPT-4.1 routing) ===")
call_model_router(
    """I'm designing a motor control system using the dsPIC33CK256MP508.
I need to implement a field-oriented control (FOC) algorithm with:
- PWM frequency: 20kHz
- Current loop bandwidth: 2kHz
- Three-phase BLDC motor, 48V bus
Please analyze the timer and PWM peripheral configuration requirements,
identify potential interrupt latency issues, and recommend the register
settings for the PWM module to achieve dead-time insertion of 500ns.""",
    complexity="high"
)