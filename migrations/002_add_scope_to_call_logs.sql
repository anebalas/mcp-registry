-- Add scope_checked to audit log so every entry records which scope was enforced.
-- Aligns with MCP spec guidance: log elevation events with the scope requested.
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS scope_checked VARCHAR(100);
