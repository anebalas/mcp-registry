## Access Request

**Team name:**

**Requested scopes** (check all that apply):
- [ ] `read:parts` — decode part attributes (make, model, category, compatibility)
- [ ] `validate:parts` — check whether a part number is active
- [ ] `admin` — view audit log and usage across all teams

**Interface you will use:**
- [ ] MCP Server (Claude Desktop, Cursor, or other MCP client)
- [ ] REST API
- [ ] CLI

**Daily call volume estimate:**

**Business justification** — what workflow or product does this enable?

**Data owner approval** — who from the owning team has signed off?

---

*Reviewer checklist:*
- [ ] Scopes are the minimum required for the stated workflow
- [ ] Daily limit is set in `scripts/seed.py` and matches the estimate above
- [ ] Key is added as a hashed entry — no plain-text key committed
- [ ] `seed.py` re-run in staging before merge
