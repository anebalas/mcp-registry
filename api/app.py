"""
REST API layer for the Part Registry.

All endpoints require an API key in the X-API-Key header.
Auth and audit logging use the same registry core as the MCP server and CLI.

Routes are synchronous (def, not async def) so FastAPI offloads them to its
thread pool, keeping psycopg2 blocking calls safe under concurrent traffic.

Endpoints:
  GET  /health                        — liveness check
  GET  /parts/{part_number}           — decode part attributes (scope: read:parts)
  GET  /parts/{part_number}/validate  — validate a part number (scope: validate:parts)
  GET  /usage                         — call log summary (scope: admin)
"""
import os
import time
import sys
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from dotenv import load_dotenv

from registry.auth import validate
from registry.logger import log_call
from registry.models import PartAttributes, PartValidation
from registry.parts import lookup_part, elapsed_ms, part_to_attributes
from registry.db import get_conn, release_conn

load_dotenv()

app = FastAPI(
    title="Part Registry API",
    description="Governed access to part decode capabilities. Requires X-API-Key header.",
    version="1.0.0",
)


def _auth(api_key: str | None, scope: str) -> dict:
    """
    Validate key and scope. Raises HTTPException on auth failure so the
    registry.auth core stays decoupled from FastAPI primitives.
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    try:
        return validate(api_key, scope)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/parts/{part_number}", response_model=PartAttributes)
def decode_part(part_number: str, x_api_key: Optional[str] = Header(default=None)):
    """
    Decode a part number — returns make, model, category, compatibility.
    Requires scope: read:parts
    """
    start = time.monotonic()
    team = "unknown"

    try:
        team_info = _auth(x_api_key, "read:parts")
        team = team_info["team"]

        part = lookup_part(part_number)

        if not part:
            log_call(team, "api:decodePart", {"part_number": part_number},
                     success=False, response_ms=elapsed_ms(start),
                     error_message="Not found", scope="read:parts")
            raise HTTPException(status_code=404, detail=f"Part '{part_number}' not found")

        log_call(team, "api:decodePart", {"part_number": part_number},
                 success=True, response_ms=elapsed_ms(start), scope="read:parts")
        return part_to_attributes(part)

    except HTTPException:
        raise
    except Exception as e:
        log_call(team, "api:decodePart", {"part_number": part_number},
                 success=False, response_ms=elapsed_ms(start),
                 error_message=str(e), scope="read:parts")
        raise


@app.get("/parts/{part_number}/validate", response_model=PartValidation)
def validate_part(part_number: str, x_api_key: Optional[str] = Header(default=None)):
    """
    Validate whether a part number exists and is active.
    Requires scope: validate:parts
    """
    start = time.monotonic()
    team = "unknown"

    try:
        team_info = _auth(x_api_key, "validate:parts")
        team = team_info["team"]

        part = lookup_part(part_number)
        is_valid = part is not None and part["is_valid"]

        log_call(team, "api:validatePart", {"part_number": part_number},
                 success=True, response_ms=elapsed_ms(start), scope="validate:parts")
        return PartValidation(part_number=part_number, valid=is_valid)

    except HTTPException:
        raise
    except Exception as e:
        log_call(team, "api:validatePart", {"part_number": part_number},
                 success=False, response_ms=elapsed_ms(start),
                 error_message=str(e), scope="validate:parts")
        raise


@app.get("/usage")
def usage(
    team: Optional[str] = Query(default=None),
    x_api_key: Optional[str] = Header(default=None),
):
    """
    Call log summary grouped by team and tool.
    Requires scope: admin
    """
    start = time.monotonic()
    req_team = "unknown"

    try:
        team_info = _auth(x_api_key, "admin")
        req_team = team_info["team"]

        filters = []
        params = []
        if team:
            filters.append("team = %s")
            params.append(team)

        where = ("WHERE " + " AND ".join(filters)) if filters else ""

        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT team, tool,
                           COUNT(*) AS total,
                           SUM(CASE WHEN success THEN 1 ELSE 0 END) AS successes,
                           SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) AS failures,
                           ROUND(AVG(response_ms)) AS avg_ms
                    FROM call_logs
                    {where}
                    GROUP BY team, tool
                    ORDER BY total DESC
                    """,
                    params
                )
                rows = cur.fetchall()
        finally:
            release_conn(conn)

        log_call(req_team, "api:usage", {"filter_team": team},
                 success=True, response_ms=elapsed_ms(start), scope="admin")

        return [
            {
                "team": r[0], "tool": r[1],
                "total": r[2], "successes": r[3],
                "failures": r[4], "avg_ms": r[5],
            }
            for r in rows
        ]

    except HTTPException:
        raise
    except Exception as e:
        log_call(req_team, "api:usage", {"filter_team": team},
                 success=False, response_ms=elapsed_ms(start),
                 error_message=str(e), scope="admin")
        raise


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.app:app",
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", 8001)),
        reload=False,
    )
