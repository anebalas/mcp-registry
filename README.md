# MCP Registry — Enterprise Governance Pattern

![Tests](https://github.com/anebalas/mcp-registry/actions/workflows/test.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Most MCP examples are hello-world demos. This is a production-grade reference implementation showing how to govern AI data access at scale.

**One registry. Three interfaces. Authentication on every call. Governance defined in code.**

### What makes this different

| Enterprise Capability | Typical MCP Demo | This Repository |
|:---|:---|:---|
| **Authentication** | None | API keys with explicit scope enforcement per team |
| **Rate Limiting** | None | Rolling 24-hour limits, enforced against the audit log |
| **Audit Logging** | None | Every call logged with team, latency, and error |
| **Compound Tooling** | Single-purpose | `getPartInfo` combines validate + decode in one round-trip |
| **Thread Safety** | `SimpleConnectionPool` | `ThreadedConnectionPool` with double-checked lock |
| **Interfaces** | MCP only | MCP + REST API + CLI sharing one registry core |
| **Tests** | None | 36 integration tests against a real database |
| **Docker** | None | `docker compose up` |

## Quick Start

```bash
# 1. Setup — install dependencies, create database, load test data
make install && make db && make seed

# 2. Verify — 36 integration tests against a real database
make test

# 3. Run — start the REST API, then try a sample request
make run-api
```

```bash
# Sample requests against the running API
curl http://localhost:8001/parts/P-1001 -H "X-API-Key: sk-finance-team-key-001"
curl http://localhost:8001/parts/P-9999/validate -H "X-API-Key: sk-compliance-team-key-002"
curl http://localhost:8001/usage -H "X-API-Key: sk-admin-key-004"
```

For the MCP server: `make run-mcp` — then add to Claude Desktop or Cursor using the config below.

---

### Add to Claude Desktop / Cursor

Paste this into your MCP client config (`claude_desktop_config.json` or `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "part-registry": {
      "command": "python",
      "args": ["-m", "mcp_server.app"],
      "env": {
        "PART_API_KEY": "sk-finance-team-key-001",
        "DATABASE_URL": "postgresql://user:password@localhost:5432/part_registry"
      }
    }
  }
}
```

Or with Docker:

```json
{
  "mcpServers": {
    "part-registry": {
      "command": "docker",
      "args": ["compose", "run", "--rm", "mcp"],
      "env": {
        "PART_API_KEY": "sk-finance-team-key-001"
      }
    }
  }
}
```

### Who this is for

- Engineers building MCP servers for internal data access
- Teams migrating from ad-hoc DB access to a governed API layer
- Anyone who wants to see what enterprise-grade MCP governance looks like in practice

### Fork and adapt

Replace the `parts` table and `decodePart`, `validatePart`, `getPartInfo` tools with your own data capability. The auth, audit log, rate limiting, and three-interface pattern carry over unchanged.

## Where This Fits

MCP tooling currently falls into three categories. This repository occupies the gap between the first two and the third.

**Reference demos** — single-purpose connectors with no authentication, no concurrency handling, and no audit trail. Built for one developer on localhost. Fine for learning the protocol, not for governing real data access.

**Cloud-native gateways** — Kubernetes-native platforms that handle routing, identity federation, and service mesh policies at the infrastructure layer. Powerful, but require significant operational overhead and assume cloud-native deployments.

**This repository** — lightweight, Python-native, runs on Docker Compose, built specifically for the problem of governing internal enterprise data access. Thread-safe connection pooling, scoped API keys, full audit logging, GitOps-driven access control, and three interfaces sharing one registry core. No cloud vendor required. Clone it, configure it, and run it against your own data layer.

If you are building a production MCP server for internal teams and need authentication, observability, and governance without standing up a platform, this is the pattern.

## Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│                            CONSUMERS                                  │
│                                                                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │  Product Mgrs   │  │   Engineers /   │  │  Apps & Services    │  │
│  │  Ops / Finance  │  │   AI Agents     │  │  (code integrations)│  │
│  │  Chat / MCP     │  │   CLI / Batch   │  │  REST clients       │  │
│  └────────┬────────┘  └────────┬────────┘  └──────────┬──────────┘  │
└───────────┼────────────────────┼──────────────────────┼─────────────┘
            │                   │                       │
            ▼                   ▼                       ▼
┌───────────────────────────────────────────────────────────────────────┐
│                         INTERFACE LAYER                               │
│                                                                       │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐ │
│  │    MCP Server    │ │    CLI Tools     │ │     REST API         │ │
│  │                  │ │                  │ │     (FastAPI)        │ │
│  │  decodePart()    │ │  part-cli        │ │                      │ │
│  │  validatePart()  │ │    decode        │ │  GET /parts/{id}     │ │
│  │  getPartInfo()   │ │    validate      │ │  GET /parts/{id}     │ │
│  │                  │ │  registry-cli    │ │       /validate      │ │
│  │  Key: env var    │ │    usage         │ │  GET /usage          │ │
│  │  PART_API_KEY    │ │    errors        │ │                      │ │
│  │                  │ │    teams         │ │  Key: X-API-Key      │ │
│  └────────┬─────────┘ └────────┬─────────┘ └──────────┬───────────┘ │
└───────────┼────────────────────┼──────────────────────┼─────────────┘
            └────────────────────┼──────────────────────┘
                                 │  All interfaces share one core
                                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│                          CONTROL PLANE                                │
│                                                                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │   auth.py       │  │   logger.py     │  │   db.py             │  │
│  │                 │  │                 │  │                     │  │
│  │  • Key hash     │  │  • INSERT every │  │  • ThreadedPool     │  │
│  │    lookup       │  │    call         │  │  • maxconn=10       │  │
│  │  • Scope check  │  │  • Swallows own │  │  • Rollback on      │  │
│  │  • Rate limit   │  │    errors —     │  │    release          │  │
│  │    (from logs)  │  │    never masks  │  │  • Double-checked   │  │
│  │                 │  │    caller error │  │    lock on init     │  │
│  └────────┬────────┘  └────────┬────────┘  └──────────┬──────────┘  │
└───────────┼────────────────────┼──────────────────────┼─────────────┘
            └────────────────────┼──────────────────────┘
                                 │
                                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│                            DATABASE                                   │
│                                                                       │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐ │
│  │      parts       │ │    api_keys      │ │     call_logs        │ │
│  │                  │ │                  │ │                      │ │
│  │  part_number (PK)│ │  team            │ │  team                │ │
│  │  make            │ │  key_hash        │ │  tool                │ │
│  │  model           │ │  scopes[]        │ │  input (JSONB)       │ │
│  │  category        │ │  rate_limit      │ │  success             │ │
│  │  compatibility   │ │                  │ │  response_ms         │ │
│  │  is_valid        │ │                  │ │  called_at           │ │
│  └──────────────────┘ └──────────────────┘ └──────────────────────┘ │
│                                                                       │
│  Teams get a key to the registry — not to the database.              │
└───────────────────────────────────────────────────────────────────────┘
```

Three interfaces share one registry core. Every call is authenticated, scoped, rate-limited, and audit-logged.

## When to Use MCP, CLI, or REST

| | MCP | CLI | REST |
|---|---|---|---|
| **Who's consuming?** | Non-technical users, AI agents with known tasks | Engineers, pipelines, exploratory agents | Applications and services |
| **Path known upfront?** | Yes — bounded capability, structured response | No — explore, observe, adjust | Yes — stable HTTP contract |
| **Cost of a mistake?** | High — regulated data, critical systems | Low — investigation, debugging | Medium — depends on caller |
| **Discoverability needed?** | Yes — agent finds it via registry | No — caller already knows what they need | No — API contract is documented |
| **Example** | PM asks "is part X compatible?" via chat | Engineer debugs why two teams get different counts | Mobile app fetches part details on scan |

The decision heuristic: MCP when the capability is known and the consumer might not be technical. CLI when the path isn't known in advance. REST for everything in between that needs a stable HTTP contract.

## Project Structure

```
part-registry/
├── registry/
│   ├── auth.py       — API key validation, scope enforcement, rate limiting
│   ├── db.py         — Thread-safe Postgres connection pool
│   ├── logger.py     — Audit log: every call recorded, failures never propagate
│   └── models.py     — Pydantic response models shared across interfaces
├── mcp_server/
│   └── app.py        — FastMCP tools: decodePart, validatePart, getPartInfo
├── api/
│   └── app.py        — FastAPI REST endpoints
├── cli/
│   ├── part_cli.py   — End-user CLI: decode (single + batch), validate
│   └── registry_cli.py — Ops CLI: query, usage, errors, teams
├── migrations/
│   └── 001_init.sql  — Schema: parts, api_keys, call_logs
├── scripts/
│   └── seed.py       — Test parts and API keys
└── tests/
    ├── test_registry.py — Auth, MCP tools, audit log (21 tests)
    └── test_api.py      — REST endpoints (15 tests)
```

## Setup

> **Note on the data layer:** In production, the registry sits in front of an Oracle stored procedure. This implementation uses PostgreSQL as a drop-in stand-in — the governance pattern (auth, audit logging, rate limiting, three interfaces) is identical regardless of what backs the registry. Swap `registry/db.py` for your own connection layer and the rest carries over unchanged.

**Prerequisites:** Python 3.11+, PostgreSQL running locally.

```bash
# 1. Create virtual environment
uv venv --python 3.12
source .venv/bin/activate   # or .venv\Scripts\activate on Windows

# 2. Install dependencies
uv pip install -r requirements.txt

# 3. Configure database
cp .env.example .env
# Edit .env and set DATABASE_URL=postgresql://user:password@localhost:5432/part_registry

# 4. Create database and run migrations
createdb part_registry
psql part_registry -f migrations/001_init.sql

# 5. Seed test data and API keys
python scripts/seed.py
```

## Authentication

Every interface requires an API key. Keys are scoped — a team can only call tools within their granted scopes.

| Team       | Key                        | Scopes                              | Daily Limit |
|------------|----------------------------|-------------------------------------|-------------|
| finance    | sk-finance-team-key-001    | read:parts, validate:parts          | 10,000      |
| compliance | sk-compliance-team-key-002 | validate:parts                      | 5,000       |
| ml-team    | sk-ml-team-key-003         | read:parts                          | 50,000      |
| admin      | sk-admin-key-004           | read:parts, validate:parts, admin   | 999,999     |

Keys are stored as SHA-256 hashes. Plain-text keys in `seed.py` are for local development only — use a secrets manager in production.

The plain-text token is never stored. On first use, `auth.py` computes `key_hash = hashlib.sha256(api_key.encode()).hexdigest()` and looks it up against the `api_keys` table. An auditing team inspecting the database sees only the hash — the raw token is unrecoverable from it.

## Identity and Audit

Every call in the audit log is attributed to a team. There are no anonymous requests — a missing or invalid key returns a 401 before any data is touched.

**Request attribution** — inspect who called what and when:

```bash
# All calls from the finance team this month
python cli/registry_cli.py usage --team finance --from 2026-06-01

# Every failed call in the last 24 hours, with the error message
python cli/registry_cli.py errors --last 24h

# Teams approaching their daily rate limit
python cli/registry_cli.py alerts
```

**Key rotation** — to rotate a team's key, update `scripts/seed.py` with a new plain-text token and re-run the seed script. The old hash is overwritten. Open a PR so the rotation has an owner and a timestamp in git history.

```bash
# After updating seed.py
python scripts/seed.py
```

**Access revocation** — to cut off a team immediately, remove their row from `scripts/seed.py` and re-run. Their key hash is deleted from `api_keys`. Every subsequent call returns 401.

```bash
# Verify they're gone
python cli/registry_cli.py teams
```

**What the audit log proves** — the `call_logs` table answers "what did the ml-team call today?" The git history answers "who approved giving them `read:parts` access and when?" Together they satisfy the two questions an auditor actually asks: what happened at runtime, and what was authorized in advance.

## Running the Interfaces

All three interfaces call the same registry core — the same auth check, the same audit log, the same database query. Only the entry point changes.

---

### 1. MCP Server — For AI Agents

The API key is read from the environment, never from a tool parameter. Credentials must not appear in the tool schema — any MCP client calling `tools/list` would see them.

```bash
PART_API_KEY=sk-finance-team-key-001 python mcp_server/app.py
```

Tools exposed to the agent:

| Tool | Scope | What it does |
|---|---|---|
| `decodePart(part_number)` | read:parts | Full attributes — make, model, category, compatibility |
| `validatePart(part_number)` | validate:parts | Active or retired — returns `valid: true/false`, never errors |
| `getPartInfo(part_number)` | read:parts | **Compound tool** — validates + decodes in one round-trip, saves agent tokens |

---

### 2. REST API — For Applications and Web Services

Same cryptographic key hash check and rate limit enforcement as the MCP server.

```bash
python api/app.py
# OpenAPI docs at http://127.0.0.1:8001/docs
```

| Method | Path | Scope | Description |
|---|---|---|---|
| GET | `/health` | none | Liveness check |
| GET | `/parts/{part_number}` | read:parts | Decode part attributes |
| GET | `/parts/{part_number}/validate` | validate:parts | Validate part number |
| GET | `/usage` | admin | Call log summary |

```bash
curl http://localhost:8001/parts/P-1001 \
  -H "X-API-Key: sk-finance-team-key-001"
```

---

### 3. CLI — For Engineers and Automation

Two utilities: `part_cli.py` for lookups and batch processing, `registry_cli.py` for operational monitoring.

**End-user (`part_cli.py`):**

```bash
# Decode a single part
python cli/part_cli.py decode --part-number P-1001 --api-key sk-finance-team-key-001

# Batch decode a CSV file — one part per row, column header: part_number
python cli/part_cli.py decode --file parts.csv --output results.json \
  --api-key sk-finance-team-key-001

# Validate a part number
python cli/part_cli.py validate-part --part-number P-9999 \
  --api-key sk-compliance-team-key-002
```

**Ops / governance (`registry_cli.py`):**

```bash
# Audit recent errors across all tools
python cli/registry_cli.py errors --last 24h

# Usage by team — who is calling what
python cli/registry_cli.py usage --team finance --from 2026-05-01

# Which teams have zero calls (not yet migrated off direct DB access)
python cli/registry_cli.py teams --inactive

# Adversarial patterns: scope denials, auth failures, rate limit warnings
python cli/registry_cli.py alerts
python cli/registry_cli.py alerts --last 7d --threshold 2
```

## Testing

```bash
# Run all tests
.venv/bin/pytest tests/ -v

# Run only registry (auth + MCP) tests
.venv/bin/pytest tests/test_registry.py -v

# Run only API tests
.venv/bin/pytest tests/test_api.py -v
```

Tests hit a real Postgres database — no mocking. This is intentional: the registry pattern is about governing real data access, and mocked tests would not catch the integration failures that matter.

**Zero-warning policy.** `pyproject.toml` promotes all warnings to errors (`"error"`). The one exception is a Starlette/httpx deprecation that fires during test collection — before any test code runs — which means a class-based filter is unreliable. The filter uses a message-pattern string instead:

```toml
[tool.pytest.ini_options]
filterwarnings = [
    "error",
    "ignore:Using `httpx` with `starlette.testclient` is deprecated:UserWarning",
]
```

This survives third-party framework updates: if the warning message changes, the filter stops matching and the CI run fails — surfacing the change rather than silently ignoring it.

## Governance Model

Most teams solve the "too many integrations" problem by adding a new integration. Twenty teams accessing the same Oracle procedure in twenty different ways — some with hardcoded credentials, some via CSV batch jobs, some through custom HTTP endpoints nobody fully understands anymore. Same data source. No identity on any call. When something breaks at 2am, there is no way to know which team caused it.

A registry fixes the connectivity problem. Governance fixes the trust problem. Without it, replacing twenty ad-hoc integrations with twenty ungoverned registry connections is not progress.

Access to the registry is managed through pull requests, not a dashboard or tickets.

**Need a new team onboarded?** Add a row to `scripts/seed.py` and open a PR using the **Access Request** template.  
**Need to change a team's scopes or rate limit?** Edit `api_keys` in `seed.py` and open a PR.  
**Need to add a new data capability?** Add the tool to `mcp_server/app.py`, a route to `api/app.py`, and open a PR using the **New Capability** template.

Every change has an owner, a reviewer, a commit hash, and a rollback path. Governance isn't a spreadsheet maintained by a security team — it's part of the software delivery lifecycle.

**PR templates** in `.github/PULL_REQUEST_TEMPLATE/` guide contributors through the right checklist for each change type. GitHub shows a template chooser when opening a new PR.

**CODEOWNERS** (`.github/CODEOWNERS`) enforces that `registry/auth.py`, `registry/db.py`, `migrations/`, and `scripts/seed.py` require registry team review on every PR — GitHub blocks merge until the designated reviewer approves. Nobody can quietly change the trust boundary.

```bash
# Example: onboard a new team
# 1. Add their key and scopes to scripts/seed.py
# 2. Run the seed script to apply
python scripts/seed.py

# 3. Open a PR — the diff is the audit trail
```

The audit log (`call_logs`) records what happened at runtime. The git history records what was authorized and by whom. Together they answer both "what did the ml-team call today?" and "who approved giving them read:parts access?"

## Design Decisions

**ThreadedConnectionPool over SimpleConnectionPool** — FastAPI runs sync handlers in a thread pool. `SimpleConnectionPool` is not thread-safe. `ThreadedConnectionPool` serializes pool operations with a lock.

**`log_call` never propagates errors** — A logging failure must not mask the original business error. `log_call` swallows its own exceptions and writes a warning to stderr instead. This means audit log gaps are possible but are always visible in stderr.

**`api_key` is an env var on the MCP server, not a tool parameter** — Tool parameters appear in the MCP schema exposed to every client. Credentials must not be visible in schema definitions. Each MCP server instance is pre-configured with one team's key.

**Rate limiting reads `call_logs`** — Rate limit state is derived from the audit log rather than a separate counter table. This keeps the schema simple and makes the limit auditable: you can always inspect the log to see why a team was blocked.

**`release_conn` always calls `rollback()`** — Connections returned to the pool may be in an aborted transaction state if a query failed mid-flight. Rolling back before return ensures the next caller always gets a clean connection.
