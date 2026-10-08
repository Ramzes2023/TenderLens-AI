"""Explicit offline SQLite -> empty PostgreSQL import. Never called by startup."""
from __future__ import annotations

import argparse
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from .backend import Database, IDENTITY_TABLES, StorageError, identifier, table_columns, table_names
from .config import DatabaseSettings, load_database_settings
from .migrations import MIGRATIONS

# Parent rows precede FK children. Never discover identifiers from user arguments.
TABLES = (
    "auth_accounts", "organizations", "organization_members", "organization_invitations",
    "company_workspaces", "company_active", "auth_sessions", "auth_telegram_links",
    "auth_password_resets", "auth_email_verifications", "tenders", "saved_opportunities",
    "discovery_search_history", "monitor_subscriptions", "monitor_seen", "rag_chunks",
    "support_tickets", "support_ticket_messages", "durable_jobs", "source_opportunities",
)
METADATA = {"schema_meta", "app_schema_migrations", "app_data_imports"}
OPTIONAL = {"rag_chunks", "support_ticket_messages", "durable_jobs", "source_opportunities"}


def validate_versions(conn, *, legacy=False):
    names = set(table_names(conn))
    expected = [(m.version, m.domain, m.checksum) for m in MIGRATIONS]
    if "app_schema_migrations" in names:
        versions = [tuple(row) if isinstance(row, sqlite3.Row) else tuple(row.values())
                    for row in conn.execute("SELECT version,domain,checksum FROM app_schema_migrations ORDER BY version")]
        if legacy:
            if any(row not in expected for row in versions):
                raise StorageError("Unsupported source schema migrations.")
        elif versions != expected:
            raise StorageError("Destination schema must be fully migrated first.")
    elif not legacy:
        raise StorageError("Destination schema must be fully migrated first.")
    if "schema_meta" not in names:
        raise StorageError("Source/destination schema version is missing.")
    version = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
    if version is None or str(version[0]) != "1":
        raise StorageError("Unsupported source/destination schema version.")


def preflight_source(conn):
    """Read-only snapshot inspection; reject unknown tables and incompatible columns."""
    if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise StorageError("Source integrity check failed.")
    if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise StorageError("Source foreign-key check failed.")
    validate_versions(conn, legacy=True)
    names = set(table_names(conn))
    if names - set(TABLES) - METADATA:
        raise StorageError("Source has unsupported tables; explicit migration review required.")
    if "durable_jobs" not in names and "app_schema_migrations" in names:
        if conn.execute("SELECT 1 FROM app_schema_migrations WHERE version=9").fetchone():
            raise StorageError("Source job schema is missing; upgrade a backed-up copy first.")
    if "source_opportunities" not in names and "app_schema_migrations" in names:
        if conn.execute("SELECT 1 FROM app_schema_migrations WHERE version=10").fetchone():
            raise StorageError("Source opportunity schema is missing; upgrade a backed-up copy first.")
    if set(TABLES) - OPTIONAL - names:
        raise StorageError("Source schema is incomplete; upgrade a backed-up copy first.")
    if "app_data_imports" in names and conn.execute("SELECT 1 FROM app_data_imports LIMIT 1").fetchone():
        raise StorageError("Source has existing import history; explicit review required.")
    # Canonical SQLite schema is built only in an isolated temporary fixture. The
    # real source remains read-only, even when it predates the migration ledger.
    with tempfile.TemporaryDirectory(prefix="valyqon-schema-") as tmp:
        template = Database(DatabaseSettings("", Path(tmp) / "schema.sqlite"))
        try:
            template.migrate()
            with closing(template.connect()) as reference:
                columns = {table: table_columns(reference, table) for table in TABLES if table in names}
                signatures = {
                    table: [(row[1], row[2].upper(), row[5]) for row in reference.execute(f"PRAGMA table_info({identifier(table)})")]
                    for table in columns
                }
        finally:
            template.close()
    counts = {}
    for table, expected in columns.items():
        if table_columns(conn, table) != expected:
            raise StorageError("Source columns differ from the supported schema.")
        signature = [(row[1], row[2].upper(), row[5]) for row in conn.execute(f"PRAGMA table_info({identifier(table)})")]
        if signature != signatures[table]:
            raise StorageError("Source column types or primary keys differ from the supported schema.")
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {identifier(table)}").fetchone()[0]
    # Enforce PostgreSQL's case-insensitive uniqueness before transferring any rows.
    for sql in (
        "SELECT 1 FROM auth_accounts GROUP BY lower(email) HAVING COUNT(*)>1 LIMIT 1",
        "SELECT 1 FROM organization_invitations WHERE accepted_at IS NULL AND revoked_at IS NULL GROUP BY organization_id,lower(email) HAVING COUNT(*)>1 LIMIT 1",
    ):
        if conn.execute(sql).fetchone():
            raise StorageError("Source email uniqueness preflight failed.")
    return columns, counts


def preflight_destination(conn, columns):
    validate_versions(conn)
    if set(table_names(conn)) - set(TABLES) - METADATA:
        raise StorageError("Destination has unsupported tables.")
    if conn.execute("SELECT 1 FROM app_data_imports LIMIT 1").fetchone():
        raise StorageError("Destination has already been imported.")
    for table in TABLES:
        if conn.execute(f"SELECT COUNT(*) FROM {identifier(table)}").fetchone()[0] != 0:
            raise StorageError("Destination must be empty; refusing merge or duplicate import.")
        if table in columns and table_columns(conn, table) != columns[table]:
            raise StorageError("Destination columns differ from source.")


def transfer(source, destination, columns, counts):
    """Caller owns one transaction across all tables, verification and marker."""
    for table in TABLES:
        if table not in columns:
            continue
        names = columns[table]
        selected = ",".join(identifier(name) for name in names)
        placeholders = ",".join("?" for _ in names)
        # PK order is deterministic, including compound and text primary keys.
        pk = [row[1] for row in sorted(source.execute(f"PRAGMA table_info({identifier(table)})"), key=lambda row: row[5]) if row[5]]
        order = ",".join(identifier(name) for name in pk)
        rows = source.execute(f"SELECT {selected} FROM {identifier(table)} ORDER BY {order}")
        while batch := rows.fetchmany(500):
            destination.executemany(f"INSERT INTO {identifier(table)}({selected}) VALUES({placeholders})",
                                   [tuple(row) for row in batch])
        actual = destination.execute(f"SELECT COUNT(*) FROM {identifier(table)}").fetchone()[0]
        if actual != counts[table]:
            raise StorageError("Migration row-count mismatch; import rolled back.")
    for table in sorted(IDENTITY_TABLES):
        # setval is not transactional in PostgreSQL. A failed import can leave
        # harmless sequence gaps; explicit IDs/data/marker still roll back.
        destination.execute(
            f"SELECT setval(pg_get_serial_sequence(?, 'id'), COALESCE((SELECT MAX(id) FROM {identifier(table)}),1), EXISTS(SELECT 1 FROM {identifier(table)}))",
            (table,),
        )


def import_sqlite(source_path: Path, database: Database, *, dry_run=True):
    if database.backend != "postgresql":
        raise StorageError("Import destination must be PostgreSQL.")
    source_path = Path(source_path).resolve()
    if not source_path.is_file():
        raise StorageError("Explicit SQLite source file does not exist.")
    # URI read-only prevents accidental creation or mutation of a source database.
    with closing(sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)) as source:
        source.row_factory = sqlite3.Row
        source.execute("PRAGMA query_only=ON")
        source.execute("BEGIN")
        columns, counts = preflight_source(source)
        with closing(database.connect()) as destination:
            if dry_run:
                # No DDL, writes, sequence changes, locks or marker in a dry run.
                preflight_destination(destination, columns)
            else:
                with destination:
                    destination.execute("BEGIN IMMEDIATE")
                    preflight_destination(destination, columns)
                    transfer(source, destination, columns, counts)
                    digest = sha256()
                    with source_path.open("rb") as source_file:
                        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
                            digest.update(chunk)
                    fingerprint = digest.hexdigest()
                    destination.execute("INSERT INTO app_data_imports(source_fingerprint,completed_at) VALUES(?,?)",
                                        (fingerprint, datetime.now(timezone.utc).isoformat()))
        return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description="VALYQON AI offline SQLite to empty PostgreSQL import")
    parser.add_argument("--source", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    database = None
    try:
        # URL only from secure environment/.env; never command-line/process-list passwords.
        database = Database(load_database_settings())
        counts = import_sqlite(args.source, database, dry_run=args.dry_run)
        print("VALYQON AI import preflight complete." if args.dry_run else "VALYQON AI import committed.")
        for table, count in counts.items():
            print(f"{table}: {count}")
        return 0
    except Exception:
        # Paths, DSNs, hashes, tokens and driver errors must not reach console output.
        print("VALYQON AI import refused or failed; verify schema, empty destination and configuration.")
        return 1
    finally:
        if database is not None:
            database.close()


if __name__ == "__main__":
    raise SystemExit(main())
