CREATE TABLE IF NOT EXISTS source_opportunities (
    source_id TEXT NOT NULL CHECK(length(source_id) BETWEEN 1 AND 64),
    external_id TEXT NOT NULL CHECK(length(external_id) BETWEEN 1 AND 500),
    notice_json TEXT NOT NULL,
    connector_version TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY(source_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_source_opportunities_recent
    ON source_opportunities(source_id,last_seen DESC,external_id);
