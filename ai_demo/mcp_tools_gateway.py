"""
MCP & Tools through the AI Gateway — Foundry agent + governed MCP server.


This file is the *agent half*. It declares an MCP tool on a Foundry Responses-API
call, but points it at the **APIM gateway URL** (not the raw MCP server). The model
decides to call `lookup_part` / `search_parts`; the call leaves Foundry, hits APIM,
and APIM does the governance:

    agent (Foundry model)
        │  tools=[{type:"mcp", server_url: <APIM>/mcp/parts, headers:{key}}]
        ▼
    APIM AI Gateway  ── authenticate (key/JWT) ─┐
                     ── allow-list approved tools┤  (ai_demo/apim/
                     ── meter + observe (emit)   ┘   mcp-tool-governance.policy.xml)
        ▼
    internal parts-lookup MCP server  (ai_demo/mcp_server/parts_lookup_server.py)

GOVERNANCE CONSIDERATIONS this demonstrates (all enforced at the gateway, not the
agent, because the agent is the thing being governed):
  * AuthN/Z      — APIM validates a subscription key (or Entra JWT) before the
                   tool is reachable; the MCP server never sees an anonymous call.
  * Tool allow-list — APIM inspects the JSON-RPC `tools/call` body and rejects any
                   tool not on the approved set (403). `allowed_tools` below is the
                   client-side mirror; the gateway is the enforcement point.
  * Metering/observability — APIM emits the same custom metric (namespace `genai`)
                   and a structured trace per tool call, so MCP usage shows up in
                   the very dashboards you already built for model tokens.
  * Egress control — a remote/3rd-party MCP server is reached only through the
                   gateway's named backend, so you can pin, rotate, rate-limit, and
                   audit it centrally.

Required env (.env in ai_demo/):
    PROJECT_ENDPOINT          Foundry project endpoint (azure-ai-projects)
    MODEL_ROUTER_DEPLOYMENT   model/deployment name (e.g. model-router)
    MCP_SERVER_GATEWAY_URL    APIM-fronted MCP URL, e.g.
                              https://wpcounty-dev-apim-mro5df.azure-api.net/mcp/parts
    APIM_SUBSCRIPTION_KEY     key APIM requires (sent as Ocp-Apim-Subscription-Key)

Run:
    uv pip install mcp                       # for the local smoke test only
    python ai_demo/mcp_server/parts_lookup_server.py   # terminal 1 (local server)
    python ai_demo/mcp_tools_gateway.py                # terminal 2 (this file)
    python ai_demo/mcp_tools_gateway.py smoke          # call the tool via the gateway,
                                                       # no Foundry needed (validates
                                                       # auth + allow-list + metering)

NOTE: when the Foundry service calls the MCP tool, `server_url` must be reachable
from Azure — i.e. the APIM **public** route in front of the MCP server. A localhost
URL is reachable only by the `smoke` path below (which runs on your machine).
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Approved tools — the allow-list the gateway enforces; mirrored here so the model
# is only ever offered the governed surface.
ALLOWED_TOOLS = ["lookup_part", "search_parts"]


# ─────────────────────────────────────────────────────────────────────────────
# Agent half: Foundry Responses API with an MCP tool pointed at the gateway.
# ─────────────────────────────────────────────────────────────────────────────
def run_agent_with_gateway_tool(user_query: str) -> None:
    """Ask the model a question it can only answer by calling the MCP tool.

    The tool is declared at the APIM gateway URL with the subscription-key header,
    so every tool call the model makes is authenticated, allow-listed, and metered
    by APIM before it reaches the parts-lookup server.
    """
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    gateway_url = os.environ["MCP_SERVER_GATEWAY_URL"]
    apim_key = os.environ["APIM_SUBSCRIPTION_KEY"]

    # Exclude env credential so blank AZURE_CLIENT_ID/SECRET in .env don't trigger
    # service-principal auth — fall back to `az login`.
    project = AIProjectClient(
        endpoint=os.environ["PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(exclude_environment_credential=True),
    )
    openai_client = project.get_openai_client()

    response = openai_client.responses.create(
        model=os.environ["MODEL_ROUTER_DEPLOYMENT"],
        input=user_query,
        instructions=(
            "You are a hardware support assistant. When asked about a specific "
            "part, you MUST use the parts-lookup tools to get authoritative specs. "
            "Do not answer specs from memory."
        ),
        tools=[
            {
                # An MCP server is just an API — declare it like any remote tool,
                # but route through the gateway so APIM governs each call.
                "type": "mcp",
                "server_label": "parts_lookup",
                "server_url": gateway_url,
                # The gateway authenticates this; the MCP server never sees an
                # unauthenticated request.
                "headers": {"Ocp-Apim-Subscription-Key": apim_key},
                # Client-side mirror of the gateway allow-list.
                "allowed_tools": ALLOWED_TOOLS,
                "require_approval": "never",
            }
        ],
    )

    print(f"\nQ: {user_query}")
    print(f"\nA: {response.output_text}\n")

    # Surface the tool calls the model made — these are exactly what the gateway
    # authenticated, allow-listed, and metered.
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", "") in ("mcp_call", "mcp_tool_call"):
            name = getattr(item, "name", "?")
            print(f"  [gateway-governed tool call] {name}")
    if response.usage is not None:
        print(f"  tokens: {response.usage.total_tokens}")
    print("-" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test: call the MCP tool directly THROUGH the gateway (no Foundry needed).
# Proves the gateway authenticates, allow-lists, and meters the call locally.
# ─────────────────────────────────────────────────────────────────────────────
async def _smoke_async() -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    gateway_url = os.environ.get("MCP_SERVER_GATEWAY_URL", "http://localhost:8000/mcp")
    apim_key = os.environ.get("APIM_SUBSCRIPTION_KEY", "")
    headers = {"Ocp-Apim-Subscription-Key": apim_key} if apim_key else None

    print(f"==> Connecting to MCP server via gateway: {gateway_url}")
    async with streamablehttp_client(gateway_url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools advertised:", [t.name for t in tools.tools])

            # An APPROVED tool — the gateway lets this through and meters it.
            result = await session.call_tool("lookup_part",
                                             {"part_number": "PIC32MZ2048EFH144"})
            # content is a union of block types; only TextContent has .text.
            first = result.content[0] if result.content else None
            print("lookup_part ->", getattr(first, "text", first) if first else result)

            # A NON-APPROVED tool — if you call one the gateway allow-list blocks,
            # APIM returns 403 before the server is touched. (Uncomment to see.)
            # await session.call_tool("delete_part", {"part_number": "X"})


def smoke_test_through_gateway() -> None:
    asyncio.run(_smoke_async())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "smoke":
        smoke_test_through_gateway()
    else:
        run_agent_with_gateway_tool(
            "Look up the PIC32MZ2048EFH144 and tell me its max clock and flash size."
        )
        run_agent_with_gateway_tool(
            "Which parts in the catalog are recommended for new designs?"
        )
