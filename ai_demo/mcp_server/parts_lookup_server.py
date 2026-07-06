"""
Internal Parts-Lookup MCP Server — the "tool" in the MCP & Tools demo.

This is a tiny Model Context Protocol (MCP) server that exposes an *internal*
parts catalog as two tools an agent can call:

    lookup_part(part_number)  -> full record for one part
    search_parts(query)       -> matching parts for a free-text query

THE WHOLE POINT: an MCP server is just an API. It speaks JSON-RPC 2.0 over HTTP
(the streamable-http transport), so the APIM AI Gateway can sit in front of it
and govern it exactly like any other backend — authenticate the caller, check the
requested tool against an allow-list, meter the call, and emit the same
observability signal. See ai_demo/apim/mcp-tool-governance.policy.xml for the
gateway half, and ai_demo/mcp_tools_gateway.py for the agent that calls it.

Run it (local, for development / smoke tests):

    uv pip install mcp           # or: uv add mcp
    python ai_demo/mcp_server/parts_lookup_server.py
    # serves streamable-http at http://localhost:8000/mcp

In production this server runs *behind* APIM (a public, governed route), so the
Foundry agent reaches it as https://<apim>.azure-api.net/mcp/parts — never the
raw server URL. "Sometimes remote" is the normal case: the gateway is what makes a
remote MCP server safe to expose to an agent.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

# FastMCP serves JSON-RPC over the streamable-http transport at path "/mcp".
mcp = FastMCP("parts-lookup", host="0.0.0.0", port=8000)

# ── Synthetic internal parts catalog (fictional spec data) ───────────────────
_PARTS: dict[str, dict] = {
    "PIC32MX270F256B": {
        "part_number": "PIC32MX270F256B",
        "family": "PIC32MX",
        "core": "MIPS32 M4K",
        "max_clock_mhz": 50,
        "flash_kb": 256,
        "ram_kb": 64,
        "operating_voltage_v": [2.3, 3.6],
        "package": "28-pin SPDIP/SOIC/SSOP/QFN",
        "status": "Active",
        "lifecycle": "Mature",
    },
    "PIC32MZ2048EFH144": {
        "part_number": "PIC32MZ2048EFH144",
        "family": "PIC32MZ EF",
        "core": "MIPS32 microAptiv (FPU)",
        "max_clock_mhz": 200,
        "flash_kb": 2048,
        "ram_kb": 512,
        "operating_voltage_v": [2.1, 3.6],
        "package": "144-pin TQFP/LQFP",
        "status": "Active",
        "lifecycle": "Recommended for new designs",
    },
    "DSPIC33CK256MP508": {
        "part_number": "dsPIC33CK256MP508",
        "family": "dsPIC33CK",
        "core": "dsPIC DSC (single-core)",
        "max_clock_mhz": 100,
        "flash_kb": 256,
        "ram_kb": 24,
        "operating_voltage_v": [3.0, 3.6],
        "package": "48/64/80-pin",
        "status": "Active",
        "lifecycle": "Recommended for new designs",
    },
}


def _key(part_number: str) -> str:
    return part_number.strip().upper().replace("-", "")


@mcp.tool()
def lookup_part(part_number: str) -> dict:
    """Return the full internal record for an exact part number.

    Args:
        part_number: e.g. "PIC32MX270F256B" (case-insensitive).
    """
    record = _PARTS.get(_key(part_number))
    if record is None:
        return {
            "found": False,
            "part_number": part_number,
            "message": "No internal record for that part number.",
        }
    return {"found": True, **record}


@mcp.tool()
def search_parts(query: str) -> list[dict]:
    """Search the internal catalog by family, package, or keyword.

    Args:
        query: free text, e.g. "PIC32MZ" or "200 MHz" or "FPU".
    """
    q = query.strip().lower()
    hits = [
        {"part_number": rec["part_number"], "family": rec["family"],
         "max_clock_mhz": rec["max_clock_mhz"], "flash_kb": rec["flash_kb"],
         "lifecycle": rec["lifecycle"]}
        for rec in _PARTS.values()
        if q in " ".join(str(v) for v in rec.values()).lower()
    ]
    return hits


if __name__ == "__main__":
    # streamable-http transport => POST JSON-RPC to http://localhost:8000/mcp
    mcp.run(transport="streamable-http")
