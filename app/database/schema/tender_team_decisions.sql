-- Authentic company-scoped tender ownership and internal approval audit.
-- Never claims official procurement authorization or an actual bid submission.
CREATE TABLE IF NOT EXISTS saved_tender_team_decisions (
    saved_opportunity_id INTEGER PRIMARY KEY REFERENCES saved_opportunities(id) ON DELETE CASCADE,
    assignee_account_id INTEGER REFERENCES auth_accounts(id) ON DELETE SET NULL,
    approval_state TEXT NOT NULL DEFAULT 'not_requested'
        CHECK(approval_state IN ('not_requested','pending','approved','rejected')),
    requested_by_account_id INTEGER REFERENCES auth_accounts(id) ON DELETE SET NULL,
    decided_by_account_id INTEGER REFERENCES auth_accounts(id) ON DELETE SET NULL,
    revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
    updated_by_account_id INTEGER NOT NULL REFERENCES auth_accounts(id) ON DELETE RESTRICT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS saved_tender_team_decision_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    saved_opportunity_id INTEGER NOT NULL REFERENCES saved_opportunities(id) ON DELETE CASCADE,
    actor_account_id INTEGER NOT NULL REFERENCES auth_accounts(id) ON DELETE RESTRICT,
    action TEXT NOT NULL CHECK(action IN ('assign','request','approve','reject','withdraw')),
    previous_state TEXT NOT NULL,
    next_state TEXT NOT NULL,
    previous_assignee_account_id INTEGER,
    next_assignee_account_id INTEGER,
    changed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saved_tender_team_decision_events
    ON saved_tender_team_decision_events(saved_opportunity_id,id DESC);
