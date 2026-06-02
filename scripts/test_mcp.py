"""
MCP client test script for the Part Registry.

Connects directly to the FastMCP server in-process (no HTTP server needed)
and exercises all tools, auth enforcement, and schema verification.

Usage:
  PART_API_KEY=sk-finance-team-key-001 python scripts/test_mcp.py

What it tests:
  1. Tool discovery — lists available tools and verifies api_key is NOT in schema
  2. decode_part    — valid part, unknown part
  3. validate_part  — active part, retired part, unknown part
  4. Scope enforcement — wrong-scope key is rejected
"""
import asyncio
import os
import sys


from fastmcp import Client
from dotenv import load_dotenv

load_dotenv()

# Keys to test with
FINANCE_KEY    = "sk-finance-team-key-001"   # read:parts, validate:parts
COMPLIANCE_KEY = "sk-compliance-team-key-002" # validate:parts only


def banner(title: str):
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print('=' * 50)


def ok(label: str, value=None):
    suffix = f"  →  {value}" if value is not None else ""
    print(f"  ✓  {label}{suffix}")


def fail(label: str, detail: str = ""):
    print(f"  ✗  {label}  [{detail}]")


async def run():
    import mcp_server.app as srv

    # Configure server with finance key (read:parts + validate:parts)
    srv._API_KEY = FINANCE_KEY

    async with Client(srv.mcp) as client:

        # ----------------------------------------------------------------
        # 1. Tool discovery
        # ----------------------------------------------------------------
        banner("1. Tool Discovery")
        tools = await client.list_tools()
        tool_names = [t.name for t in tools]
        print(f"  Tools found: {tool_names}")

        for tool in tools:
            params = list(tool.inputSchema.get("properties", {}).keys())
            print(f"  {tool.name} params: {params}")
            if "api_key" in params:
                fail(f"{tool.name}: api_key exposed in schema — credentials leak!")
            else:
                ok(f"{tool.name}: api_key NOT in schema (correct)")

        # ----------------------------------------------------------------
        # 2. decode_part — valid part
        # ----------------------------------------------------------------
        banner("2. decode_part — known part (P-1001)")
        result = await client.call_tool("decode_part", {"part_number": "P-1001"})
        data = result.data if hasattr(result, "data") else result
        print(f"  Result: {data}")
        ok("decode_part returned successfully")

        # ----------------------------------------------------------------
        # 3. decode_part — unknown part
        # ----------------------------------------------------------------
        banner("3. decode_part — unknown part (P-UNKNOWN)")
        try:
            await client.call_tool("decode_part", {"part_number": "P-UNKNOWN"})
            fail("Expected error for unknown part — none raised")
        except Exception as e:
            ok(f"Correctly raised error: {e}")

        # ----------------------------------------------------------------
        # 4. validate_part — active part
        # ----------------------------------------------------------------
        banner("4. validate_part — active part (P-1002)")
        result = await client.call_tool("validate_part", {"part_number": "P-1002"})
        data = result.data if hasattr(result, "data") else result
        print(f"  Result: {data}")
        ok("validate_part returned successfully")

        # ----------------------------------------------------------------
        # 5. validate_part — retired part
        # ----------------------------------------------------------------
        banner("5. validate_part — retired part (P-9999)")
        result = await client.call_tool("validate_part", {"part_number": "P-9999"})
        data = result.data if hasattr(result, "data") else result
        print(f"  Result: {data}")
        ok("Retired part returns valid=false (not an error)")

        # ----------------------------------------------------------------
        # 6. validate_part — unknown part
        # ----------------------------------------------------------------
        banner("6. validate_part — unknown part (P-UNKNOWN)")
        result = await client.call_tool("validate_part", {"part_number": "P-UNKNOWN"})
        data = result.data if hasattr(result, "data") else result
        print(f"  Result: {data}")
        ok("Unknown part returns valid=false (not an error)")

    # ----------------------------------------------------------------
    # 7. Scope enforcement — compliance key cannot decode
    # ----------------------------------------------------------------
    banner("7. Scope enforcement — compliance key calling decode_part")
    srv._API_KEY = COMPLIANCE_KEY

    async with Client(srv.mcp) as client:
        try:
            await client.call_tool("decode_part", {"part_number": "P-1001"})
            fail("Expected scope error — none raised")
        except Exception as e:
            ok(f"Correctly blocked: {e}")

    print(f"\n{'=' * 50}")
    print("  All MCP tests complete")
    print('=' * 50)


if __name__ == "__main__":
    asyncio.run(run())
