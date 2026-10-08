CREATE TABLE IF NOT EXISTS organizations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 200),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        created_by_account_id INTEGER NOT NULL REFERENCES auth_accounts(id) ON DELETE RESTRICT,
        personal_account_id INTEGER UNIQUE REFERENCES auth_accounts(id) ON DELETE RESTRICT);
CREATE TABLE IF NOT EXISTS organization_members(
        organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        account_id INTEGER NOT NULL REFERENCES auth_accounts(id) ON DELETE RESTRICT,
        role TEXT NOT NULL CHECK(role IN ('owner','admin','member','viewer')),
        created_at TEXT NOT NULL,
        PRIMARY KEY(organization_id,account_id));
CREATE INDEX IF NOT EXISTS idx_org_members_account ON organization_members(account_id,organization_id);
CREATE TABLE IF NOT EXISTS organization_invitations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        email TEXT NOT NULL COLLATE NOCASE,
        role TEXT NOT NULL CHECK(role IN ('admin','member','viewer')),
        token_hash TEXT NOT NULL UNIQUE,
        invited_by_account_id INTEGER NOT NULL REFERENCES auth_accounts(id) ON DELETE RESTRICT,
        expires_at TEXT NOT NULL,
        accepted_at TEXT,
        revoked_at TEXT,
        created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_org_invites_org
           ON organization_invitations(
               organization_id,
               created_at DESC
           );
CREATE INDEX IF NOT EXISTS idx_org_invites_email
           ON organization_invitations(
               email,
               expires_at
           );
CREATE UNIQUE INDEX IF NOT EXISTS uq_org_pending_invite_email
           ON organization_invitations(
               organization_id,
               email
           )
           WHERE accepted_at IS NULL
             AND revoked_at IS NULL;
