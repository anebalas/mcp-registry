"""
registry.auth — API key validation, scope enforcement, and rate limiting.

validate() is the single gate every interface (MCP, REST, CLI) passes through.
It checks three things in one DB round-trip:
  1. The key exists (hash match)
  2. The key has the required scope
  3. The team has not exceeded their daily call limit (derived from call_logs)

Rate limits are stored per team in api_keys.rate_limit and enforced by
counting rows in call_logs for the last 24 hours. This keeps the schema
simple and makes rate-limit decisions auditable.
"""
import hashlib
from registry.db import get_conn, release_conn


def _hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def validate(api_key: str, required_scope: str) -> dict:
    """
    Returns team info if the key is valid, has the required scope,
    and is within its daily rate limit.
    Raises ValueError on any auth or rate-limit failure.
    """
    if not api_key:
        raise ValueError("Missing API key")

    key_hash = _hash_key(api_key)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT team, scopes, rate_limit FROM api_keys WHERE key_hash = %s",
                (key_hash,)
            )
            row = cur.fetchone()

            if not row:
                raise ValueError("Invalid API key")

            team, scopes, rate_limit = row

            if required_scope not in scopes:
                raise ValueError(f"Insufficient permissions: missing scope '{required_scope}'")

            # Enforce daily rate limit against the audit log
            cur.execute(
                """
                SELECT COUNT(*) FROM call_logs
                WHERE team = %s
                  AND called_at >= NOW() - INTERVAL '1 day'
                """,
                (team,)
            )
            call_count = cur.fetchone()[0]
            if call_count >= rate_limit:
                raise ValueError(
                    f"Rate limit exceeded: {call_count}/{rate_limit} calls in the last 24 hours"
                )
    finally:
        release_conn(conn)

    return {"team": team, "scopes": scopes, "rate_limit": rate_limit}
