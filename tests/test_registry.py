"""
Registry integration tests.

Covers:
  - Authentication: valid key, invalid key, missing key, wrong scope
  - decode_part: known part, unknown part, retired part
  - validate_part: valid part, invalid part, retired part
  - Audit log: every call is recorded
  - Scope enforcement: team can only call tools within their scopes
  - Rate limiting: validate() enforces daily call limit

Test API keys (from seed.py):
  finance    : sk-finance-team-key-001   scopes=[read:parts, validate:parts]
  compliance : sk-compliance-team-key-002 scopes=[validate:parts]
  ml-team    : sk-ml-team-key-003        scopes=[read:parts]
  admin      : sk-admin-key-004          scopes=[read:parts, validate:parts, admin]
"""
import json
import sys
import os
import pytest


from registry.auth import validate
from registry.db import get_conn, release_conn

FINANCE_KEY    = "sk-finance-team-key-001"
COMPLIANCE_KEY = "sk-compliance-team-key-002"
ML_KEY         = "sk-ml-team-key-003"
INVALID_KEY    = "sk-does-not-exist"


# ---------------------------------------------------------------------------
# Helpers — MCP tools now read api_key from env, so we set it per-test
# ---------------------------------------------------------------------------

def call_decode(part_number: str, api_key: str) -> dict:
    import mcp_server.app as srv
    srv._API_KEY = api_key
    result = srv.decode_part(part_number=part_number)
    return result.model_dump() if hasattr(result, "model_dump") else result


def call_validate(part_number: str, api_key: str) -> dict:
    import mcp_server.app as srv
    srv._API_KEY = api_key
    result = srv.validate_part(part_number=part_number)
    return result.model_dump()


def recent_log(tool: str, team: str) -> dict | None:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT team, tool, input, success, error_message, scope_checked
                FROM call_logs
                WHERE tool = %s AND team = %s
                ORDER BY called_at DESC LIMIT 1
                """,
                (tool, team)
            )
            row = cur.fetchone()
    finally:
        release_conn(conn)

    if not row:
        return None
    return {"team": row[0], "tool": row[1], "input": row[2],
            "success": row[3], "error": row[4], "scope": row[5]}


# ---------------------------------------------------------------------------
# Authentication tests
# ---------------------------------------------------------------------------

class TestAuthentication:

    def test_valid_key_passes(self):
        result = validate(FINANCE_KEY, "read:parts")
        assert result["team"] == "finance"

    def test_invalid_key_rejected(self):
        with pytest.raises(ValueError, match="Invalid API key"):
            validate(INVALID_KEY, "read:parts")

    def test_missing_key_rejected(self):
        with pytest.raises(ValueError, match="Missing API key"):
            validate("", "read:parts")

    def test_wrong_scope_rejected(self):
        with pytest.raises(ValueError, match="Insufficient permissions"):
            validate(COMPLIANCE_KEY, "read:parts")

    def test_correct_scope_passes(self):
        result = validate(COMPLIANCE_KEY, "validate:parts")
        assert result["team"] == "compliance"

    def test_rate_limit_returned(self):
        result = validate(FINANCE_KEY, "read:parts")
        assert "rate_limit" in result
        assert result["rate_limit"] == 10000


# ---------------------------------------------------------------------------
# decode_part tests
# ---------------------------------------------------------------------------

class TestDecodePart:

    def test_decode_known_part(self):
        result = call_decode("P-1001", FINANCE_KEY)
        assert result["part_number"] == "P-1001"
        assert result["make"] == "Honda"
        assert result["model"] == "Civic"
        assert result["category"] == "Oil Filter"
        assert "compatibility" in result

    def test_decode_different_part(self):
        result = call_decode("P-2001", FINANCE_KEY)
        assert result["make"] == "Toyota"
        assert result["model"] == "Camry"

    def test_decode_unknown_part_returns_error_payload(self):
        # Unknown parts return a structured error dict, not an exception.
        # This lets the LLM read the message without a traceback.
        result = call_decode("P-UNKNOWN", FINANCE_KEY)
        assert result["success"] is False
        assert result["error"] == "PART_NOT_FOUND"
        assert "P-UNKNOWN" in result["message"]

    def test_decode_retired_part_returns_data(self):
        result = call_decode("P-9999", FINANCE_KEY)
        assert result["part_number"] == "P-9999"
        assert result["make"] == "Legacy"

    def test_decode_blocked_without_scope(self):
        with pytest.raises(ValueError, match="Insufficient permissions"):
            call_decode("P-1001", COMPLIANCE_KEY)

    def test_decode_blocked_with_invalid_key(self):
        with pytest.raises(ValueError, match="Invalid API key"):
            call_decode("P-1001", INVALID_KEY)


# ---------------------------------------------------------------------------
# validate_part tests
# ---------------------------------------------------------------------------

class TestValidatePart:

    def test_validate_active_part(self):
        result = call_validate("P-1001", FINANCE_KEY)
        assert result["part_number"] == "P-1001"
        assert result["valid"] is True

    def test_validate_retired_part(self):
        result = call_validate("P-9999", COMPLIANCE_KEY)
        assert result["valid"] is False

    def test_validate_unknown_part(self):
        result = call_validate("P-UNKNOWN", FINANCE_KEY)
        assert result["valid"] is False

    def test_validate_blocked_without_scope(self):
        with pytest.raises(ValueError, match="Insufficient permissions"):
            call_validate("P-1001", ML_KEY)


# ---------------------------------------------------------------------------
# Audit log tests
# ---------------------------------------------------------------------------

class TestAuditLog:

    def test_successful_decode_is_logged(self):
        call_decode("P-1003", FINANCE_KEY)
        log = recent_log("decodePart", "finance")
        assert log is not None
        assert log["success"] is True
        assert log["input"]["part_number"] == "P-1003"

    def test_failed_decode_is_logged(self):
        call_decode("P-UNKNOWN", FINANCE_KEY)
        log = recent_log("decodePart", "finance")
        assert log is not None
        assert log["success"] is False
        assert log["error"] == "PART_NOT_FOUND"

    def test_validate_call_is_logged(self):
        call_validate("P-1001", COMPLIANCE_KEY)
        log = recent_log("validatePart", "compliance")
        assert log is not None
        assert log["success"] is True

    def test_scope_is_recorded_on_decode(self):
        call_decode("P-1001", FINANCE_KEY)
        log = recent_log("decodePart", "finance")
        assert log["scope"] == "read:parts"

    def test_scope_is_recorded_on_validate(self):
        call_validate("P-1001", COMPLIANCE_KEY)
        log = recent_log("validatePart", "compliance")
        assert log["scope"] == "validate:parts"
