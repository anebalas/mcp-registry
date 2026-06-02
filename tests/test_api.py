"""
REST API integration tests.

Covers:
  - Health check
  - GET /parts/{part_number}         — decode, auth, scope, 404
  - GET /parts/{part_number}/validate — validate, auth, scope
  - GET /usage                        — admin scope enforcement
"""
import sys
import os
import pytest
from fastapi.testclient import TestClient


from api.app import app

client = TestClient(app)

FINANCE_KEY    = "sk-finance-team-key-001"
COMPLIANCE_KEY = "sk-compliance-team-key-002"
ML_KEY         = "sk-ml-team-key-003"
ADMIN_KEY      = "sk-admin-key-004"
INVALID_KEY    = "sk-does-not-exist"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:

    def test_health_returns_ok(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /parts/{part_number}
# ---------------------------------------------------------------------------

class TestDecodePart:

    def test_decode_known_part(self):
        r = client.get("/parts/P-1001", headers={"X-API-Key": FINANCE_KEY})
        assert r.status_code == 200
        body = r.json()
        assert body["part_number"] == "P-1001"
        assert body["make"] == "Honda"
        assert body["model"] == "Civic"
        assert body["category"] == "Filter"
        assert "compatibility" in body

    def test_decode_unknown_part_returns_404(self):
        r = client.get("/parts/P-UNKNOWN", headers={"X-API-Key": FINANCE_KEY})
        assert r.status_code == 404

    def test_decode_missing_key_returns_401(self):
        r = client.get("/parts/P-1001")
        assert r.status_code == 401

    def test_decode_invalid_key_returns_403(self):
        r = client.get("/parts/P-1001", headers={"X-API-Key": INVALID_KEY})
        assert r.status_code == 403

    def test_decode_wrong_scope_returns_403(self):
        # compliance has validate:parts only
        r = client.get("/parts/P-1001", headers={"X-API-Key": COMPLIANCE_KEY})
        assert r.status_code == 403

    def test_decode_retired_part_returns_data(self):
        # P-9999 exists but is retired — decode still returns attributes
        r = client.get("/parts/P-9999", headers={"X-API-Key": FINANCE_KEY})
        assert r.status_code == 200
        assert r.json()["make"] == "Legacy"


# ---------------------------------------------------------------------------
# GET /parts/{part_number}/validate
# ---------------------------------------------------------------------------

class TestValidatePart:

    def test_validate_active_part(self):
        r = client.get("/parts/P-1001/validate", headers={"X-API-Key": COMPLIANCE_KEY})
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_validate_retired_part(self):
        r = client.get("/parts/P-9999/validate", headers={"X-API-Key": COMPLIANCE_KEY})
        assert r.status_code == 200
        assert r.json()["valid"] is False

    def test_validate_unknown_part(self):
        r = client.get("/parts/P-UNKNOWN/validate", headers={"X-API-Key": COMPLIANCE_KEY})
        assert r.status_code == 200
        assert r.json()["valid"] is False

    def test_validate_wrong_scope_returns_403(self):
        # ml-team has read:parts only
        r = client.get("/parts/P-1001/validate", headers={"X-API-Key": ML_KEY})
        assert r.status_code == 403

    def test_validate_missing_key_returns_401(self):
        r = client.get("/parts/P-1001/validate")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /usage
# ---------------------------------------------------------------------------

class TestUsage:

    def test_usage_accessible_with_admin_key(self):
        r = client.get("/usage", headers={"X-API-Key": ADMIN_KEY})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_usage_blocked_without_admin_scope(self):
        r = client.get("/usage", headers={"X-API-Key": FINANCE_KEY})
        assert r.status_code == 403

    def test_usage_blocked_with_invalid_key(self):
        r = client.get("/usage", headers={"X-API-Key": INVALID_KEY})
        assert r.status_code == 403
