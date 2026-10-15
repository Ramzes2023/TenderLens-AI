"""Additive organization schema/backfill helpers; caller owns the transaction."""
from datetime import datetime, timezone
from app.database.backend import table_exists, table_columns


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


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
    from pathlib import Path
    schema = Path(__file__).resolve().parents[1] / "database" / "schema" / "organizations.sql"
    for statement in schema.read_text(encoding="utf-8").split(";"):
        if statement.strip():
            conn.execute(statement)

    if table_exists(conn, "company_workspaces"):
        columns = set(table_columns(conn, "company_workspaces"))
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
