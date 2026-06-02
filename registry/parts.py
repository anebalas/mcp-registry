"""
registry.parts — Shared data access and timing helpers.

Imported by mcp_server/app.py, api/app.py, cli/part_cli.py, and tests.
Keeping queries and shared utilities here means a schema change is one edit.
"""
import time
from registry.db import get_conn, release_conn
from registry.models import PartAttributes


def elapsed_ms(start: float) -> int:
    """Convert a time.monotonic() start time to elapsed milliseconds."""
    return int((time.monotonic() - start) * 1000)


def part_to_attributes(part: dict) -> PartAttributes:
    """Build a PartAttributes model from a lookup_part() result dict."""
    return PartAttributes(
        part_number=part["part_number"],
        make=part["make"],
        model=part["model"],
        category=part["category"],
        compatibility=part["compatibility"],
    )


def lookup_part(part_number: str) -> dict | None:
    """
    Fetch a single part by part_number. Returns None if not found.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT part_number, make, model, category, compatibility, is_valid
                FROM parts
                WHERE part_number = %s
                """,
                (part_number,)
            )
            row = cur.fetchone()
    finally:
        release_conn(conn)

    if not row:
        return None

    return {
        "part_number":   row[0],
        "make":          row[1],
        "model":         row[2],
        "category":      row[3],
        "compatibility": row[4],
        "is_valid":      row[5],
    }
