"""Connection-level helpers: callers own the transaction; no production runner."""
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def table_exists(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def ensure_personal(conn, account_id):
    timestamp = now()
    conn.execute("""INSERT INTO organizations(name,created_at,updated_at,created_by_account_id,personal_account_id)
                    VALUES (?,?,?,?,?) ON CONFLICT(personal_account_id) DO NOTHING""",
                 (f"Personal workspace {account_id}", timestamp, timestamp, account_id, account_id))
    org_id = conn.execute("SELECT id FROM organizations WHERE personal_account_id=?", (account_id,)).fetchone()[0]
    # Do not reset an existing member's role during repeated migration.
    conn.execute("""INSERT INTO organization_members(organization_id,account_id,role,created_at)
                    VALUES (?,?,'owner',?) ON CONFLICT(organization_id,account_id) DO NOTHING""",
                 (org_id, account_id, timestamp))
    return org_id


def backfill_companies(conn, owner_user_id=None):
    if not table_exists(conn, "auth_accounts") or not table_exists(conn, "company_workspaces"):
        return

    owner_filter = ""
    params = ()
    if owner_user_id is not None:
        owner_filter = " AND company_workspaces.owner_user_id=?"
        params = (int(owner_user_id),)

    conn.execute(f"""UPDATE company_workspaces SET organization_id=(
        SELECT o.id FROM auth_accounts a
        JOIN organizations o ON o.personal_account_id=a.id
        JOIN organization_members m ON m.organization_id=o.id AND m.account_id=a.id
        WHERE a.owner_user_id=company_workspaces.owner_user_id)
        WHERE organization_id IS NULL{owner_filter} AND
        (SELECT COUNT(*) FROM auth_accounts a
         JOIN organizations o ON o.personal_account_id=a.id
         JOIN organization_members m ON m.organization_id=o.id AND m.account_id=a.id
         WHERE a.owner_user_id=company_workspaces.owner_user_id)=1""", params)


def migrate(conn):
    # BEGIN IMMEDIATE is held by caller, including ALTER and backfill.
    conn.execute("""CREATE TABLE IF NOT EXISTS organizations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 200),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        created_by_account_id INTEGER NOT NULL REFERENCES auth_accounts(id) ON DELETE RESTRICT,
        personal_account_id INTEGER UNIQUE REFERENCES auth_accounts(id) ON DELETE RESTRICT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS organization_members(
        organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        account_id INTEGER NOT NULL REFERENCES auth_accounts(id) ON DELETE RESTRICT,
        role TEXT NOT NULL CHECK(role IN ('owner','admin','member','viewer')),
        created_at TEXT NOT NULL,
        PRIMARY KEY(organization_id,account_id))""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_org_members_account ON organization_members(account_id,organization_id)")
    if table_exists(conn, "company_workspaces"):
        columns = {row[1] for row in conn.execute("PRAGMA table_info(company_workspaces)")}
        if "organization_id" not in columns:
            conn.execute("ALTER TABLE company_workspaces ADD COLUMN organization_id INTEGER REFERENCES organizations(id) ON DELETE RESTRICT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_company_org ON company_workspaces(organization_id)")
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS uq_company_org_name
               ON company_workspaces(organization_id, name)
               WHERE organization_id IS NOT NULL"""
        )
    if table_exists(conn, "auth_accounts"):
        for row in conn.execute("SELECT id FROM auth_accounts").fetchall():
            ensure_personal(conn, row[0])
        backfill_companies(conn)
