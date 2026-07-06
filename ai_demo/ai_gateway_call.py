"""
Custom AI Demo — Call through APIM AI Gateway.
APIM subscription key replaces project credential for cross-team enforcement.Same SDK, different endpoint.
"""

import os
from dotenv import load_dotenv
from openai import AzureOpenAI  # APIM exposes OpenAI-compatible endpoint

load_dotenv()

# ── APIM client — OpenAI-compatible surface exposed by APIM ──────────────
# APIM_ENDPOINT is the gateway URL; APIM_SUBSCRIPTION_KEY is the team key.
# APIM's OpenAI-compatible path accepts the Responses API (v1 stable route).
client = AzureOpenAI(
    azure_endpoint=os.environ["APIM_ENDPOINT"],
    api_key=os.environ["APIM_SUBSCRIPTION_KEY"],
    api_version="2025-04-01-preview",  # latest stable API version
    default_headers={
        # Team attribution header — APIM policy reads this for chargeback metrics
        "x-team-id": os.environ["TEAM_ID"],
    },
)

def call_via_apim(user_query: str, deployment: str) -> None:
    response = client.chat.completions.create(
        model=deployment,  # APIM routes to the named Foundry deployment
        messages=[
            {"role": "system", "content": "You are a Custom Technology technical support assistant."},
            {"role": "user", "content": user_query},
        ],
        max_tokens=1000,
    )

    # APIM injects response headers with token consumption for chargeback
    content = response.choices[0].message.content or ""
    print(f"Completion: {content[:200]}...")
    if response.usage is not None:
        print(f"Tokens used: {response.usage.total_tokens}")
    else:
        print("Tokens used: n/a")

# Same queries — APIM handles auth, rate limiting, and chargeback attribution
call_via_apim(
    "What is the difference between PIC32MZ and PIC32MX product families?",
    deployment="model-router"
)