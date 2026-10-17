-- Tenant-scoped tender workflow and immutable stage-change evidence. Notes are not copied into audit entries.
CREATE TABLE IF NOT EXISTS saved_opportunity_workflow (
    saved_opportunity_id INTEGER PRIMARY KEY REFERENCES saved_opportunities(id) ON DELETE CASCADE,
    stage TEXT NOT NULL CHECK(stage IN ('new','reviewing','preparing','submitted','won','lost','archived')),
    note TEXT NOT NULL DEFAULT '' CHECK(length(note) <= 2000),
    revision INTEGER NOT NULL CHECK(revision >= 1),
    updated_by_account_id INTEGER NOT NULL REFERENCES auth_accounts(id) ON DELETE RESTRICT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS saved_opportunity_workflow_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    saved_opportunity_id INTEGER NOT NULL REFERENCES saved_opportunities(id) ON DELETE CASCADE,
    actor_account_id INTEGER NOT NULL REFERENCES auth_accounts(id) ON DELETE RESTRICT,
    previous_stage TEXT NOT NULL,
    next_stage TEXT NOT NULL,
    note_changed INTEGER NOT NULL CHECK(note_changed IN (0,1)),
    changed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saved_workflow_events_recent
    ON saved_opportunity_workflow_events(saved_opportunity_id,id DESC);
