CREATE TABLE IF NOT EXISTS durable_jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL CHECK(length(job_type) BETWEEN 1 AND 100),
    state TEXT NOT NULL CHECK(state IN ('queued','running','succeeded','failed','cancelled')),
    account_id INTEGER REFERENCES auth_accounts(id) ON DELETE RESTRICT,
    organization_id INTEGER REFERENCES organizations(id) ON DELETE RESTRICT,
    company_id INTEGER REFERENCES company_workspaces(id) ON DELETE RESTRICT,
    payload_json TEXT NOT NULL,
    result_json TEXT,
    priority INTEGER NOT NULL CHECK(priority BETWEEN -100 AND 100),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0 AND attempt_count <= max_attempts),
    max_attempts INTEGER NOT NULL CHECK(max_attempts BETWEEN 1 AND 20),
    available_at BIGINT NOT NULL,
    created_at BIGINT NOT NULL,
    started_at BIGINT,
    finished_at BIGINT,
    lease_expires_at BIGINT,
    lease_token_hash TEXT,
    worker_id TEXT,
    failure_code TEXT CHECK(failure_code IN ('handler_error','permanent_failure','unknown_type','lease_expired','invalid_result')),
    idempotency_hash TEXT,
    CHECK(organization_id IS NULL OR account_id IS NOT NULL),
    CHECK(company_id IS NULL OR organization_id IS NOT NULL),
    CHECK((state='running' AND lease_expires_at IS NOT NULL AND lease_token_hash IS NOT NULL AND worker_id IS NOT NULL)
       OR (state<>'running' AND lease_expires_at IS NULL AND lease_token_hash IS NULL AND worker_id IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_jobs_claim ON durable_jobs(priority DESC,created_at,id) WHERE state='queued';
CREATE INDEX IF NOT EXISTS idx_jobs_expired ON durable_jobs(lease_expires_at,id) WHERE state='running';
CREATE INDEX IF NOT EXISTS idx_jobs_scope ON durable_jobs(account_id,organization_id,company_id,created_at,id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_idempotency ON durable_jobs(idempotency_hash)
    WHERE idempotency_hash IS NOT NULL AND state IN ('queued','running','succeeded');
