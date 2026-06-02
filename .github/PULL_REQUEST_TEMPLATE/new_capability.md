## New Capability

**Capability name** (e.g. `decodePartsBatch`):

**Interface(s) affected:**
- [ ] MCP Server (`mcp_server/app.py`)
- [ ] REST API (`api/app.py`)
- [ ] CLI (`cli/part_cli.py`)

**Required scope** — new or existing?

**What it does** — one sentence:

**Why this can't be served by an existing tool:**

**Data accessed** — which tables or external systems?

**Write operation?** (requires additional security review)
- [ ] Yes
- [ ] No

---

*Reviewer checklist:*
- [ ] Tool added to all relevant interfaces, or omission is intentional and documented
- [ ] `log_call()` called on every code path (success and failure)
- [ ] New scope added to `migrations/001_init.sql` if required
- [ ] Integration tests added in `tests/`
- [ ] `mcp.json` updated if MCP tool was added or modified
