CREATE TABLE IF NOT EXISTS synchronous_usage (
    id TEXT PRIMARY KEY,
    tenant_key TEXT NOT NULL,
    operation TEXT NOT NULL,
    admitted_at BIGINT NOT NULL CHECK(admitted_at >= 0),
    expires_at BIGINT NOT NULL,
    finished_at BIGINT
);
CREATE INDEX IF NOT EXISTS idx_sync_usage_window ON synchronous_usage(tenant_key, admitted_at);
CREATE INDEX IF NOT EXISTS idx_sync_usage_active ON synchronous_usage(tenant_key, finished_at, expires_at);
