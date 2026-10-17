-- Durable, tenant-scoped activity evidence. No tender content or private notes.
CREATE TABLE IF NOT EXISTS organization_activity_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 company_id INTEGER NOT NULL,
 actor_account_id INTEGER NOT NULL REFERENCES auth_accounts(id) ON DELETE RESTRICT,
 action TEXT NOT NULL CHECK(action IN ('tender_saved','tender_refreshed','tender_removed','export_csv_generated','export_xlsx_generated')),
 saved_opportunity_id INTEGER,
 item_count INTEGER CHECK(item_count IS NULL OR (item_count >= 0 AND item_count <= 200)),
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_organization_activity_scope
 ON organization_activity_events(organization_id,company_id,id DESC);
