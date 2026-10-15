CREATE TABLE IF NOT EXISTS scoring_public_revisions (
    revision TEXT PRIMARY KEY CHECK(length(revision)=64),
    source_id TEXT NOT NULL,
    external_id TEXT NOT NULL,
    notice_json TEXT NOT NULL,
    connector_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scoring_snapshots (
    identity TEXT PRIMARY KEY CHECK(length(identity)=64),
    account_id INTEGER NOT NULL REFERENCES auth_accounts(id) ON DELETE RESTRICT,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    company_id INTEGER NOT NULL REFERENCES company_workspaces(id) ON DELETE CASCADE,
    profile_digest TEXT NOT NULL CHECK(length(profile_digest)=64),
    engine_version TEXT NOT NULL,
    configuration_json TEXT NOT NULL,
    source_counts_json TEXT NOT NULL,
    candidate_count INTEGER NOT NULL CHECK(candidate_count BETWEEN 0 AND 500)
);
CREATE INDEX IF NOT EXISTS idx_scoring_snapshot_scope
    ON scoring_snapshots(account_id,organization_id,company_id,identity);
CREATE TABLE IF NOT EXISTS scoring_candidates (
    snapshot_id TEXT NOT NULL REFERENCES scoring_snapshots(identity) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 499),
    revision TEXT NOT NULL REFERENCES scoring_public_revisions(revision) ON DELETE RESTRICT,
    PRIMARY KEY(snapshot_id,ordinal),
    UNIQUE(snapshot_id,revision)
);
CREATE TABLE IF NOT EXISTS scoring_results (
    job_id TEXT NOT NULL REFERENCES durable_jobs(id) ON DELETE CASCADE,
    snapshot_id TEXT NOT NULL REFERENCES scoring_snapshots(identity) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 499),
    source_id TEXT NOT NULL,
    external_id TEXT NOT NULL,
    score REAL CHECK(score BETWEEN 0 AND 100),
    completeness INTEGER NOT NULL CHECK(completeness BETWEEN 0 AND 100),
    scoring_json TEXT NOT NULL,
    calculated_at BIGINT NOT NULL,
    PRIMARY KEY(job_id,source_id,external_id),
    UNIQUE(job_id,ordinal)
);
CREATE INDEX IF NOT EXISTS idx_scoring_results_page
    ON scoring_results(job_id,score DESC,completeness DESC,ordinal);
