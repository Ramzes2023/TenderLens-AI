"""Offline import security regressions using real migrations and SQLite checks."""
from contextlib import closing

import pytest

from app.database.backend import Database, StorageError
from app.database.config import DatabaseSettings
from app.database.import_sqlite import preflight_destination, preflight_source, transfer
from app.database.migrations import MIGRATIONS


@pytest.fixture
def migrated(tmp_path):
    database = Database(DatabaseSettings('', tmp_path / 'source.sqlite'))
    database.migrate()
    with closing(database.connect()) as conn:
        yield conn
    database.close()


def test_migration14_recognized_and_observations_preserved(migrated, tmp_path):
    rows = [('eis_223', 'notice', revision, '{}', 'adapter-r1',
             '2026-10-13T00:00:00Z', '{}') for revision in ('r1', 'r2')]
    migrated.executemany('INSERT INTO source_notice_observations VALUES(?,?,?,?,?,?,?)', rows)
    columns, counts = preflight_source(migrated)
    assert counts['source_notice_observations'] == 2
    destination = Database(DatabaseSettings('', tmp_path / 'destination.sqlite'))
    destination.migrate()
    try:
        with closing(destination.connect()) as conn:
            preflight_destination(conn, columns)

            class SQLiteTransferDestination:
                # SQLite has no PostgreSQL sequences. All row SQL, constraints
                # and count verification still run against the real database.
                def execute(self, sql, params=()):
                    if sql.startswith('SELECT setval('):
                        return conn.execute('SELECT 1')
                    return conn.execute(sql, params)

                def executemany(self, sql, batch):
                    return conn.executemany(sql, batch)

            with conn:
                transfer(migrated, SQLiteTransferDestination(), columns, counts)
            actual = conn.execute('SELECT * FROM source_notice_observations ORDER BY revision').fetchall()
            assert [tuple(row) for row in actual] == rows
            with pytest.raises(StorageError, match='must be empty'):
                preflight_destination(conn, columns)
    finally:
        destination.close()


@pytest.mark.parametrize('mutation', [
    'ALTER TABLE source_notice_observations ADD COLUMN extra TEXT',
    'CREATE INDEX extra_observation_index ON source_notice_observations(revision)',
    'DROP INDEX idx_source_notice_observations_recent',
    '''CREATE TRIGGER extra_observation_trigger AFTER INSERT ON source_notice_observations
       BEGIN SELECT 1; END''',
])
def test_modified_observation_schema_rejected(migrated, mutation):
    migrated.execute(mutation)
    with pytest.raises(StorageError, match='observation schema differs'):
        preflight_source(migrated)


@pytest.mark.parametrize('replacement', [
    MIGRATIONS[13].sql.replace(' NOT NULL', ''),
    MIGRATIONS[13].sql.replace('notice_json TEXT', 'notice_json INTEGER'),
    MIGRATIONS[13].sql.replace('PRIMARY KEY(source_id, external_id, revision)',
                              'PRIMARY KEY(source_id, external_id)'),
    MIGRATIONS[13].sql.replace('comparison_json TEXT NOT NULL',
                              "comparison_json TEXT NOT NULL CHECK(comparison_json='{}')"),
])
def test_untrusted_constraints_and_types_rejected(migrated, replacement):
    migrated.execute('DROP TABLE source_notice_observations')
    migrated.executescript(replacement)
    with pytest.raises(StorageError, match='observation schema differs'):
        preflight_source(migrated)


@pytest.mark.parametrize('mutation, message', [
    ('CREATE TABLE unrelated(id INTEGER PRIMARY KEY)', 'unsupported tables'),
    ('CREATE TABLE source_observations(id INTEGER PRIMARY KEY)', 'unsupported tables'),
    ('DROP TABLE source_notice_observations', 'known migration 14'),
    ('DELETE FROM app_schema_migrations WHERE version=14', 'known migration 14'),
    ("UPDATE app_schema_migrations SET checksum='untrusted' WHERE version=14", 'schema migrations'),
    ("UPDATE schema_meta SET value='999' WHERE key='schema_version'", 'schema version'),
    ('ALTER TABLE source_opportunities ADD COLUMN extra TEXT', 'columns differ'),
])
def test_import_guards_remain_closed(migrated, mutation, message):
    migrated.execute(mutation)
    with pytest.raises(StorageError, match=message):
        preflight_source(migrated)


@pytest.mark.parametrize('ledger', [True, False])
def test_legacy_without_observations_remains_compatible(migrated, ledger):
    migrated.execute('DROP TABLE source_notice_observations')
    migrated.execute('DELETE FROM app_schema_migrations WHERE version=14')
    if not ledger:
        migrated.execute('DROP TABLE app_schema_migrations')
    columns, counts = preflight_source(migrated)
    assert 'source_notice_observations' not in columns
    assert 'source_notice_observations' not in counts


def test_preflight_is_read_only(migrated):
    migrated.commit()
    before = migrated.total_changes
    migrated.execute('PRAGMA query_only=ON')
    columns, counts = preflight_source(migrated)
    assert 'source_notice_observations' in columns
    assert counts['source_notice_observations'] == 0
    assert migrated.total_changes == before


def test_real_foreign_key_guard(migrated):
    migrated.commit()
    migrated.execute('PRAGMA foreign_keys=OFF')
    migrated.execute("INSERT INTO organization_members(organization_id,account_id,role,created_at) "
                     "VALUES(999,999,'owner','2026-10-13')")
    with pytest.raises(StorageError, match='foreign-key'):
        preflight_source(migrated)


def test_real_integrity_guard(migrated):
    # A real CHECK violation introduced with SQLite's repair pragma must still
    # fail quick_check; the guard itself is never mocked.
    migrated.execute('PRAGMA ignore_check_constraints=ON')
    migrated.execute("INSERT INTO source_opportunities VALUES('', 'id', '{}', 'v1', 'now', 'now')")
    migrated.execute('PRAGMA ignore_check_constraints=OFF')
    with pytest.raises(StorageError, match='integrity'):
        preflight_source(migrated)
