CREATE TABLE IF NOT EXISTS quota_admissions (
    job_id TEXT PRIMARY KEY REFERENCES durable_jobs(id) ON DELETE RESTRICT,
    tenant_key TEXT NOT NULL CHECK(length(tenant_key) BETWEEN 9 AND 32),
    admitted_at BIGINT NOT NULL CHECK(admitted_at >= 0)
);
CREATE INDEX IF NOT EXISTS idx_quota_tenant_window ON quota_admissions(tenant_key,admitted_at);
INSERT INTO quota_admissions(job_id,tenant_key,admitted_at)
    SELECT id, CASE WHEN organization_id IS NOT NULL
        THEN 'organization:' || CAST(organization_id AS TEXT)
        ELSE 'account:' || CAST(account_id AS TEXT) END, created_at
    FROM durable_jobs WHERE account_id IS NOT NULL ON CONFLICT DO NOTHING;
