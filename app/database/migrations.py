"""Ordered, additive, transaction-owned schema migrations for both backends."""
from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .backend import StorageError, table_exists, table_columns

SCHEMA_DIR = Path(__file__).with_name("schema")


@dataclass(frozen=True)
class Migration:
    version: int
    domain: str

    @property
    def sql(self):
        return (SCHEMA_DIR / (self.domain + ".sql")).read_text(encoding="utf-8")

    @property
    def checksum(self):
        # Upgrade implementation revision is part of the immutable migration identity.
        return sha256(("24S1A-v1:" + self.sql).encode()).hexdigest()


MIGRATIONS = tuple(Migration(i, domain) for i, domain in enumerate(
    ("auth", "organizations", "companies", "tenders", "monitoring", "rag", "support", "operations", "jobs", "opportunities", "scoring", "quotas"), 1
))


def _script(conn, script):
    # Unlike sqlite3.executescript, executing fixed statements preserves our transaction.
    for sql in script.split(";"):
        if sql.strip():
            conn.execute(sql)


def _apply(conn, migration, backend):
    from app.organizations.migration import migrate as organization_upgrade
    if migration.domain == "organizations":
        organization_upgrade(conn)
    else:
        _script(conn, migration.sql)
    if migration.domain == "auth":
        columns = set(table_columns(conn, "auth_accounts"))
        if "email_verified" not in columns:
            conn.execute("ALTER TABLE auth_accounts ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1 CHECK(email_verified IN (0,1))")
        if "email_verified_at" not in columns:
            conn.execute("ALTER TABLE auth_accounts ADD COLUMN email_verified_at TEXT")
        if backend == "postgresql":
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_auth_email_lower ON auth_accounts(lower(email))")
    if migration.domain == "companies":
        organization_upgrade(conn)
    if migration.domain == "tenders":
        current = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
        if current is not None and current[0] != "1":
            raise StorageError("Unsupported legacy database schema version.")
        conn.execute("INSERT INTO schema_meta(key,value) VALUES('schema_version','1') ON CONFLICT(key) DO NOTHING")
    if migration.domain in {"organizations", "companies"} and backend == "postgresql":
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_org_pending_email_lower ON organization_invitations(organization_id,lower(email)) WHERE accepted_at IS NULL AND revoked_at IS NULL")


def migrate(database, domain=None):
    if domain is not None and domain not in {m.domain for m in MIGRATIONS}:
        raise StorageError("Unknown schema migration domain.")
    # PostgreSQL always creates dependencies in FK order. SQLite standalone repositories
    # retain partial-schema legacy test/development contracts.
    selected = MIGRATIONS if domain is None or database.backend == "postgresql" else tuple(
        m for m in MIGRATIONS if m.domain == domain or (domain == "auth" and m.domain == "organizations")
    )
    with closing(database.connect()) as conn:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            if table_exists(conn, "schema_meta"):
                legacy_version = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
                if legacy_version is not None and str(legacy_version[0]) != "1":
                    raise StorageError("Unsupported legacy database schema version.")
            conn.execute("CREATE TABLE IF NOT EXISTS app_schema_migrations(version INTEGER PRIMARY KEY, domain TEXT NOT NULL, checksum TEXT NOT NULL)")
            existing = {row[0]: (row[1], row[2]) for row in conn.execute("SELECT version,domain,checksum FROM app_schema_migrations ORDER BY version")}
            known = {m.version: (m.domain, m.checksum) for m in MIGRATIONS}
            if any(known.get(version) != identity for version, identity in existing.items()):
                raise StorageError("Unsupported or changed database schema migration.")
            for migration in selected:
                if migration.version in existing:
                    continue
                _apply(conn, migration, database.backend)
                conn.execute("INSERT INTO app_schema_migrations(version,domain,checksum) VALUES(?,?,?)",
                             (migration.version, migration.domain, migration.checksum))
            # Existing account/company backfill is idempotent and must also cover
            # legacy tables initialized separately before accounts.
            if domain in {None, "auth", "organizations", "companies"}:
                from app.organizations.migration import ensure_personal, backfill_companies
                if table_exists(conn, "auth_accounts") and table_exists(conn, "organizations"):
                    for row in conn.execute("SELECT id FROM auth_accounts ORDER BY id").fetchall():
                        ensure_personal(conn, row[0])
                    backfill_companies(conn)


def main():
    from .backend import Database
    from .config import load_database_settings
    database = None
    try:
        database = Database(load_database_settings())
        database.migrate()
        print("VALYQON AI schema migrations complete.")
        return 0
    except Exception:
        print("VALYQON AI schema migration failed; verify configuration and schema.")
        return 1
    finally:
        if database is not None:
            database.close()


if __name__ == "__main__":
    raise SystemExit(main())
