-- Account-specific named filter presets, bound to one active organization/company.
-- Pure client-side post-fetch filtering; no implied source subscription or daily delivery.
CREATE TABLE IF NOT EXISTS saved_search_filters (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 company_id INTEGER NOT NULL,
 account_id INTEGER NOT NULL REFERENCES auth_accounts(id) ON DELETE CASCADE,
 name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 80),
 filters_json TEXT NOT NULL CHECK(length(filters_json) BETWEEN 2 AND 2000),
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(organization_id,company_id,account_id,name)
);
CREATE INDEX IF NOT EXISTS idx_saved_search_filters_scope
 ON saved_search_filters(organization_id,company_id,account_id,updated_at DESC,id DESC);
