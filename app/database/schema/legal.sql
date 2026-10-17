CREATE TABLE IF NOT EXISTS account_legal_acceptances (
    account_id INTEGER NOT NULL,
    document TEXT NOT NULL CHECK(document IN ('offer','personal_data','marketing')),
    document_version TEXT NOT NULL,
    granted INTEGER NOT NULL CHECK(granted IN (0,1)),
    recorded_at TEXT NOT NULL,
    origin TEXT NOT NULL,
    PRIMARY KEY(account_id,document,document_version),
    FOREIGN KEY(account_id) REFERENCES auth_accounts(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_legal_account ON account_legal_acceptances(account_id,document);
