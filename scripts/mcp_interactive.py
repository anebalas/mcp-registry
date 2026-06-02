"""
Interactive MCP test client for the Part Registry.

Discovers available tools from the server, then lets you call
any tool with just a part number — one call at a time.

Usage:
    python scripts/mcp_interactive.py
"""
import asyncio
import os
import sys


from fastmcp import Client
from dotenv import load_dotenv

load_dotenv()

FINANCE_KEY = "sk-finance-team-key-001"


def print_tools(tools):
    for t in tools:
        schema     = t.inputSchema
        properties = schema.get("properties", {})
        required   = schema.get("required", [])
        docstring  = (t.description or "").strip().replace("\n", " ")
        print(f"  Tool      : {t.name}")
        print(f"  Docstring : {docstring}")
        print(f"  Parameters:")
        for param, meta in properties.items():
            ptype    = meta.get("type", "any")
            req      = " (required)" if param in required else " (optional)"
            pdesc    = meta.get("description", "")
            desc_str = f"  — {pdesc}" if pdesc else ""
            print(f"    - {param}: {ptype}{req}{desc_str}")
        print()


async def run():
    import mcp_server.app as srv
    srv._API_KEY = FINANCE_KEY

    async with Client(srv.mcp) as client:

        tools = await client.list_tools()
        tool_map = {t.name: t for t in tools}

        print("\nPart Registry — MCP Interactive Client")
        print("=" * 40)
        print(f"Connected. {len(tools)} tool(s) discovered:\n")
        print_tools(tools)

        print("=" * 40)
        print("Commands:")
        for name in tool_map:
            print(f"  {name} <part_number>")
        print("  tools  — list available tools")
        print("  quit")
        print("=" * 40)

        while True:
            try:
                raw = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye.")
                break

            if not raw or raw.lower() in ("quit", "exit", "q"):
                print("Bye.")
                break

            if raw.lower() == "tools":
                fresh_tools = await client.list_tools()
                print(f"\n{len(fresh_tools)} tool(s) available:\n")
                print_tools(fresh_tools)
                continue

            parts = raw.split(maxsplit=1)

            if len(parts) == 1 and parts[0].startswith("P-"):
                tool_name   = "decodePart"
                part_number = parts[0]
            elif len(parts) == 2:
                tool_name, part_number = parts
            else:
                print("  Usage: <tool_name> <part_number>  or just <part_number>")
                continue

            if tool_name not in tool_map:
                print(f"  Unknown tool '{tool_name}'. Available: {list(tool_map)}")
                continue

            try:
                result = await client.call_tool(tool_name, {"part_number": part_number})
                print(f"\n  {result.data}")
            except Exception as e:
                print(f"\n  Error: {e}")


if __name__ == "__main__":
    asyncio.run(run())
