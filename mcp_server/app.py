"""
mcp_server.app — FastMCP tool definitions for the Part Registry.

The API key is read from the PART_API_KEY environment variable at startup,
NOT from a tool parameter. Tool parameters appear in the MCP schema and are
visible to every client — credentials must not be there.

Each deployed instance of this server is pre-configured for one team:
  PART_API_KEY=sk-finance-team-key-001 python mcp_server/app.py

Tools:
  decodePart(part_number)    — decode attributes  (scope: read:parts)
  validatePart(part_number)  — active/retired flag (scope: validate:parts)
  getPartInfo(part_number)   — validate + decode in one call (scope: read:parts)
"""
import os
import time
from typing import Annotated
from pydantic import Field
from fastmcp import FastMCP
from dotenv import load_dotenv

from registry.auth import validate
from registry.logger import log_call
from registry.models import PartAttributes, PartValidation, PartInfo
from registry.parts import lookup_part, elapsed_ms, part_to_attributes

load_dotenv()

mcp = FastMCP("part-registry", version="1.0.0")

_API_KEY = os.getenv("PART_API_KEY", "")

PartNumberField = Annotated[
    str,
    Field(
        description=(
            "The part number to look up (e.g. 'P-1001'). "
            "Must be a valid registry identifier — uppercase letters, "
            "a hyphen, and trailing digits. Match this exact pattern."
        ),
        examples=["P-1001", "P-1002", "A-4920"],
    ),
]


def _get_team(required_scope: str) -> str:
    if not _API_KEY:
        raise ValueError("PART_API_KEY environment variable is not set on the server")
    team_info = validate(_API_KEY, required_scope)
    return team_info["team"]



@mcp.tool(name="decodePart")
def decode_part(part_number: PartNumberField) -> dict | PartAttributes:
    """
    Use this tool to decode a part number and retrieve its full attributes:
    make, model, category, and vehicle compatibility range.
    Call this when a user asks what a part number refers to, which vehicles
    it fits, or what category of component it is.
    Requires scope: read:parts.
    """
    start = time.monotonic()
    team = "unknown"

    try:
        team = _get_team("read:parts")
        part = lookup_part(part_number)

        # Return a structured payload instead of raising — lets the LLM
        # read the message cleanly and inform the user without a traceback.
        if not part:
            log_call(team=team, tool="decodePart",
                     input_data={"part_number": part_number},
                     success=False,
                     response_ms=elapsed_ms(start),
                     error_message="PART_NOT_FOUND",
                     scope="read:parts")
            return {
                "success": False,
                "error": "PART_NOT_FOUND",
                "message": f"Part number '{part_number}' does not exist in the registry.",
            }

        result = PartAttributes(
            part_number=part["part_number"],
            make=part["make"],
            model=part["model"],
            category=part["category"],
            compatibility=part["compatibility"],
        )
        log_call(team=team, tool="decodePart",
                 input_data={"part_number": part_number},
                 success=True,
                 response_ms=elapsed_ms(start),
                 scope="read:parts")
        return result

    except Exception as e:
        log_call(team=team, tool="decodePart",
                 input_data={"part_number": part_number},
                 success=False,
                 response_ms=elapsed_ms(start),
                 error_message=str(e),
                 scope="read:parts")
        raise


@mcp.tool(name="validatePart")
def validate_part(part_number: PartNumberField) -> PartValidation:
    """
    Use this tool to check whether a part number exists in the registry
    and is currently active (not retired or discontinued).
    Call this before processing an order, intake form, or compliance check
    to confirm the part number is valid before proceeding.
    Returns valid: true or valid: false — never raises an error for unknown parts.
    Requires scope: validate:parts.
    """
    start = time.monotonic()
    team = "unknown"

    try:
        team = _get_team("validate:parts")
        part = lookup_part(part_number)
        is_valid = part is not None and part["is_valid"]

        result = PartValidation(part_number=part_number, valid=is_valid)
        log_call(team=team, tool="validatePart",
                 input_data={"part_number": part_number},
                 success=True,
                 response_ms=elapsed_ms(start),
                 scope="validate:parts")
        return result

    except Exception as e:
        log_call(team=team, tool="validatePart",
                 input_data={"part_number": part_number},
                 success=False,
                 response_ms=elapsed_ms(start),
                 error_message=str(e),
                 scope="validate:parts")
        raise


@mcp.tool(name="getPartInfo")
def get_part_info(part_number: PartNumberField) -> PartInfo:
    """
    Use this tool when you need both the validity status AND full attributes
    of a part in a single call. Combines validatePart and decodePart into one
    round-trip. Call this for order processing, intake workflows, or any
    scenario where you need to confirm a part is active before using its data.
    Returns valid, make, model, category, and compatibility together.
    Requires scope: read:parts.
    """
    start = time.monotonic()
    team = "unknown"

    try:
        team = _get_team("read:parts")
        part = lookup_part(part_number)

        if part:
            result = PartInfo(
                part_number=part["part_number"],
                valid=part["is_valid"],
                make=part["make"],
                model=part["model"],
                category=part["category"],
                compatibility=part["compatibility"],
            )
        else:
            result = PartInfo(
                part_number=part_number,
                valid=False,
                make=None,
                model=None,
                category=None,
                compatibility=None,
            )

        log_call(team=team, tool="getPartInfo",
                 input_data={"part_number": part_number},
                 success=True,
                 response_ms=elapsed_ms(start),
                 scope="read:parts")
        return result

    except Exception as e:
        log_call(team=team, tool="getPartInfo",
                 input_data={"part_number": part_number},
                 success=False,
                 response_ms=elapsed_ms(start),
                 error_message=str(e),
                 scope="read:parts")
        raise


if __name__ == "__main__":
    # stdio transport — required for Claude Desktop, Cursor, and other
    # MCP clients that launch the server as a subprocess.
    # For HTTP mode (testing, docker): mcp.run(host=..., port=...)
    mcp.run()
