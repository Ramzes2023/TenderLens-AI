-- Scoped opt-in reminder preferences; no implied subscriptions.
CREATE TABLE IF NOT EXISTS deadline_alert_preferences (
 account_id INTEGER NOT NULL REFERENCES auth_accounts(id) ON DELETE CASCADE,
 organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 company_id INTEGER NOT NULL,
 email_enabled INTEGER NOT NULL DEFAULT 0 CHECK(email_enabled IN (0,1)),
 telegram_enabled INTEGER NOT NULL DEFAULT 0 CHECK(telegram_enabled IN (0,1)),
 updated_at TEXT NOT NULL,
 PRIMARY KEY(account_id,organization_id,company_id)
);
CREATE INDEX IF NOT EXISTS idx_deadline_prefs_enabled
 ON deadline_alert_preferences(organization_id,company_id,email_enabled,telegram_enabled);
-- First-claim-wins protects against repeat sends in concurrent workers.
CREATE TABLE IF NOT EXISTS deadline_alert_receipts (
 account_id INTEGER NOT NULL,
 organization_id INTEGER NOT NULL,
 company_id INTEGER NOT NULL,
 source TEXT NOT NULL,
 external_id TEXT NOT NULL,
 deadline TEXT NOT NULL,
 lead_hours INTEGER NOT NULL CHECK(lead_hours IN (48,24)),
 channel TEXT NOT NULL CHECK(channel IN ('email','telegram')),
 state TEXT NOT NULL CHECK(state IN ('pending','sent','failed')),
 claimed_at TEXT NOT NULL,
 sent_at TEXT,
 PRIMARY KEY(account_id,organization_id,company_id,source,external_id,deadline,lead_hours,channel)
);
