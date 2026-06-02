-- Parts table (stand-in for Oracle stored procedure)
CREATE TABLE IF NOT EXISTS parts (
    part_number     VARCHAR(50) PRIMARY KEY,
    make            VARCHAR(100),
    model           VARCHAR(100),
    category        VARCHAR(100),
    compatibility   TEXT,
    is_valid        BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- API keys per team (hashed, never stored plain)
CREATE TABLE IF NOT EXISTS api_keys (
    id          SERIAL PRIMARY KEY,
    team        VARCHAR(100) NOT NULL,
    key_hash    VARCHAR(64) NOT NULL UNIQUE,
    scopes      TEXT[] NOT NULL DEFAULT '{}',
    rate_limit  INTEGER NOT NULL DEFAULT 1000,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Audit log: every call recorded
CREATE TABLE IF NOT EXISTS call_logs (
    id              SERIAL PRIMARY KEY,
    team            VARCHAR(100),
    tool            VARCHAR(100) NOT NULL,
    input           JSONB,
    success         BOOLEAN NOT NULL,
    error_message   TEXT,
    response_ms     INTEGER,
    called_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_call_logs_team ON call_logs(team);
CREATE INDEX IF NOT EXISTS idx_call_logs_tool ON call_logs(tool);
CREATE INDEX IF NOT EXISTS idx_call_logs_called_at ON call_logs(called_at);
-- Composite index for rate limit query: WHERE team = %s AND called_at >= NOW() - INTERVAL '1 day'
CREATE INDEX IF NOT EXISTS idx_call_logs_team_called_at ON call_logs(team, called_at);
