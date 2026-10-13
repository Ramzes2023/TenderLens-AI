CREATE TABLE IF NOT EXISTS source_notice_observations (
    source_id TEXT NOT NULL,
    external_id TEXT NOT NULL,
    revision TEXT NOT NULL,
    notice_json TEXT NOT NULL,
    connector_version TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    comparison_json TEXT NOT NULL,
    PRIMARY KEY(source_id, external_id, revision)
);
CREATE INDEX IF NOT EXISTS idx_source_notice_observations_recent
    ON source_notice_observations(source_id, external_id, observed_at DESC);
