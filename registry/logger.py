"""
registry.logger — Audit log for every registry call.

log_call() is intentionally fire-and-forget: it catches all exceptions
internally and writes a warning to stderr rather than propagating. This
ensures a DB or pool failure during logging never masks the original
business error in the caller's except block.

If log_call fails, the stderr warning is the signal — the missing audit
entry is the gap. Silent logging gaps are preferable to silent business
errors.
"""
import json
import logging
from registry.db import get_conn, release_conn

_logger = logging.getLogger(__name__)


def log_call(team: str, tool: str, input_data: dict, success: bool,
             response_ms: int, error_message: str = None, scope: str = None):
    try:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO call_logs (team, tool, input, success, response_ms, error_message, scope_checked)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (team, tool, json.dumps(input_data), success, response_ms, error_message, scope)
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            release_conn(conn)
    except Exception as exc:
        # Log to stderr so the audit failure is visible but never propagates
        # to the caller — a logging failure must not mask the original error.
        _logger.warning("audit log failed: %s", exc)
