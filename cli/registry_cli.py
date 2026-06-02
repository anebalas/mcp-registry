"""
registry-cli: ops and engineering CLI for querying registry internals.

Usage:
  registry-cli query --part-number P-1001 --include-metadata
  registry-cli usage --team finance --from 2026-05-01
  registry-cli errors --tool validate_part --last 24h
  registry-cli teams --inactive
"""
import os
import sys
import json
from datetime import datetime, timedelta
import click
from tabulate import tabulate


from registry.db import get_conn, release_conn
from dotenv import load_dotenv

load_dotenv()


@click.group()
def cli():
    pass


@cli.command()
@click.option("--part-number", "-p", required=True)
@click.option("--include-metadata", is_flag=True, default=False,
              help="Include validity status and created_at")
def query(part_number, include_metadata):
    """Direct registry query for a part number."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT part_number, make, model, category, compatibility,
                       is_valid, created_at
                FROM parts WHERE part_number = %s
                """,
                (part_number,)
            )
            row = cur.fetchone()
    finally:
        release_conn(conn)

    if not row:
        click.echo(f"Part '{part_number}' not found in registry.")
        return

    result = {
        "part_number":   row[0],
        "make":          row[1],
        "model":         row[2],
        "category":      row[3],
        "compatibility": row[4],
    }

    if include_metadata:
        result["is_valid"]   = row[5]
        result["created_at"] = str(row[6])

    click.echo(json.dumps(result, indent=2))


@cli.command()
@click.option("--team", "-t", default=None, help="Filter by team name")
@click.option("--from", "from_date", default=None,
              help="Start date (YYYY-MM-DD). Defaults to last 30 days.")
@click.option("--tool", default=None, help="Filter by tool name")
def usage(team, from_date, tool):
    """Show call volume from the audit log, grouped by team and tool."""
    if from_date:
        since = datetime.strptime(from_date, "%Y-%m-%d")
    else:
        since = datetime.now() - timedelta(days=30)

    filters = ["called_at >= %s"]
    params = [since]

    if team:
        filters.append("team = %s")
        params.append(team)
    if tool:
        filters.append("tool = %s")
        params.append(tool)

    where = " AND ".join(filters)

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
                WHERE {where}
                GROUP BY team, tool
                ORDER BY total DESC
                """,
                params
            )
            rows = cur.fetchall()
    finally:
        release_conn(conn)

    if not rows:
        click.echo("No calls found for the given filters.")
        return

    click.echo(tabulate(
        rows,
        headers=["Team", "Tool", "Total", "Success", "Failures", "Avg ms"],
        tablefmt="simple"
    ))


@cli.command()
@click.option("--tool", default=None, help="Filter by tool name")
@click.option("--last", "last_hours", default="24h",
              help="Time window, e.g. 24h, 48h, 7d. Default: 24h")
def errors(tool, last_hours):
    """Show recent failed calls from the audit log."""
    hours = _parse_duration(last_hours)
    since = datetime.now() - timedelta(hours=hours)

    filters = ["called_at >= %s", "success = FALSE"]
    params = [since]

    if tool:
        filters.append("tool = %s")
        params.append(tool)

    where = " AND ".join(filters)

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT called_at, team, tool, input, error_message
                FROM call_logs
                WHERE {where}
                ORDER BY called_at DESC
                LIMIT 50
                """,
                params
            )
            rows = cur.fetchall()
    finally:
        release_conn(conn)

    if not rows:
        click.echo("No errors found.")
        return

    click.echo(tabulate(
        [(str(r[0])[:19], r[1], r[2], str(r[3]), r[4]) for r in rows],
        headers=["Timestamp", "Team", "Tool", "Input", "Error"],
        tablefmt="simple"
    ))


@cli.command("teams")
@click.option("--inactive", is_flag=True, default=False,
              help="Show teams with zero calls in the last 30 days — useful for tracking "
                   "teams yet to migrate off a legacy system onto this registry.")
def teams(inactive):
    """Show registered teams and their activity."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if inactive:
                # Teams with an API key but zero calls in the last 30 days
                cur.execute(
                    """
                    SELECT k.team, k.scopes, k.rate_limit,
                           COUNT(l.id) AS calls_last_30d
                    FROM api_keys k
                    LEFT JOIN call_logs l
                        ON l.team = k.team
                        AND l.called_at >= NOW() - INTERVAL '30 days'
                    GROUP BY k.team, k.scopes, k.rate_limit
                    HAVING COUNT(l.id) = 0
                    ORDER BY k.team
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT k.team, k.scopes, k.rate_limit,
                           COUNT(l.id) AS calls_last_30d
                    FROM api_keys k
                    LEFT JOIN call_logs l
                        ON l.team = k.team
                        AND l.called_at >= NOW() - INTERVAL '30 days'
                    GROUP BY k.team, k.scopes, k.rate_limit
                    ORDER BY calls_last_30d DESC
                    """
                )
            rows = cur.fetchall()
    finally:
        release_conn(conn)

    if not rows:
        label = "inactive teams" if inactive else "teams"
        click.echo(f"No {label} found.")
        return

    if inactive:
        click.echo("Teams with zero registry calls in the last 30 days:")

    click.echo(tabulate(
        [(r[0], ", ".join(r[1]), r[2], r[3]) for r in rows],
        headers=["Team", "Scopes", "Rate Limit", "Calls (30d)"],
        tablefmt="simple"
    ))


@cli.command("alerts")
@click.option("--last", "last_hours", default="24h",
              help="Time window, e.g. 24h, 48h, 7d. Default: 24h")
@click.option("--threshold", default=3,
              help="Minimum failure count to surface. Default: 3")
def alerts(last_hours, threshold):
    """Surface suspicious patterns: repeated scope denials, auth failures, rate limit warnings."""
    hours = _parse_duration(last_hours)
    since = datetime.now() - timedelta(hours=hours)

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Teams repeatedly hitting scope they don't have
            cur.execute(
                """
                SELECT team, scope_checked, COUNT(*) AS failures
                FROM call_logs
                WHERE called_at >= %s
                  AND success = FALSE
                  AND error_message ILIKE %s
                  AND team != 'unknown'
                GROUP BY team, scope_checked
                HAVING COUNT(*) >= %s
                ORDER BY failures DESC
                """,
                (since, "%Insufficient permissions%", threshold)
            )
            scope_denials = cur.fetchall()

            # Invalid key attempts — team is 'unknown' on auth failure
            cur.execute(
                """
                SELECT COUNT(*) AS failures,
                       MIN(called_at) AS first_seen,
                       MAX(called_at) AS last_seen
                FROM call_logs
                WHERE called_at >= %s
                  AND success = FALSE
                  AND error_message ILIKE %s
                """,
                (since, "%Invalid API key%")
            )
            auth_row = cur.fetchone()

            # Teams above 80% of their daily rate limit
            cur.execute(
                """
                SELECT k.team, k.rate_limit,
                       COUNT(l.id) AS calls_today,
                       ROUND(COUNT(l.id)::numeric / k.rate_limit * 100, 1) AS pct_used
                FROM api_keys k
                LEFT JOIN call_logs l
                    ON l.team = k.team
                    AND l.called_at >= NOW() - INTERVAL '1 day'
                GROUP BY k.team, k.rate_limit
                HAVING COUNT(l.id)::numeric / k.rate_limit >= 0.8
                ORDER BY pct_used DESC
                """
            )
            rate_warnings = cur.fetchall()
    finally:
        release_conn(conn)

    found_any = False

    if scope_denials:
        found_any = True
        click.echo(f"\n[SCOPE DENIALS] Teams repeatedly hitting unauthorized scopes (last {last_hours}):")
        click.echo(tabulate(
            [(r[0], r[1], r[2]) for r in scope_denials],
            headers=["Team", "Scope Attempted", "Failures"],
            tablefmt="simple"
        ))

    if auth_row and auth_row[0] >= threshold:
        found_any = True
        click.echo(
            f"\n[AUTH FAILURES] {auth_row[0]} invalid key attempts in the last {last_hours} "
            f"— first at {str(auth_row[1])[:19]}, last at {str(auth_row[2])[:19]}"
        )

    if rate_warnings:
        found_any = True
        click.echo(f"\n[RATE LIMIT] Teams above 80% of daily limit:")
        click.echo(tabulate(
            [(r[0], r[1], r[2], f"{r[3]}%") for r in rate_warnings],
            headers=["Team", "Daily Limit", "Calls Today", "% Used"],
            tablefmt="simple"
        ))

    if not found_any:
        click.echo(f"No alerts in the last {last_hours}.")


def _parse_duration(value: str) -> int:
    """Convert '24h', '7d' etc. to hours."""
    value = value.strip().lower()
    if value.endswith("d"):
        return int(value[:-1]) * 24
    if value.endswith("h"):
        return int(value[:-1])
    return int(value)


if __name__ == "__main__":
    cli()
