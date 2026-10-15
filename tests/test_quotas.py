"""Offline synthetic tenant admission, recovery, and security tests."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import pytest
from app.auth import AuthRepository
from app.organizations import OrganizationRepository
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.database.migrations import MIGRATIONS
from app.jobs import JobRepository, JobScope, JobValueError
from app.quotas import Limits, QuotaSettings, QuotaExceeded, load_quota_settings
from app.quotas.admission import lock


@pytest.fixture
def tenant_queue(tmp_path):
    db = Database(DatabaseSettings('', tmp_path / 'quota.db'))
    now = [datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp()]
    repo = JobRepository(db, clock=lambda: now[0], quotas=QuotaSettings(True, Limits(5, 8, 3)))
    repo.initialize()
    a = AuthRepository(db).create_account('quota@example.test', 'synthetic')
    org = OrganizationRepository(db).default_for_account(a.id)
    yield repo, JobScope(a.id, org.id), now
    db.close()


def enqueue(repo, scope, **kwargs):
    return repo.enqueue('fixture.work', {}, scope=scope, **kwargs)


def rows(repo, table):
    with closing(repo.database.connect()) as conn:
        return conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]


def test_atomic_concurrent_admission_and_restart(tenant_queue):
    repo, scope, now = tenant_queue
    def submit(_):
        other = JobRepository(repo.database, clock=lambda: now[0], quotas=repo.quotas)
        try:
            return enqueue(other, scope)
        except QuotaExceeded:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = list(pool.map(submit, range(16)))
    assert sum(j is not None for j in jobs) == 3
    assert rows(repo, 'durable_jobs') == rows(repo, 'quota_admissions') == 3
    with pytest.raises(QuotaExceeded):
        enqueue(JobRepository(repo.database, quotas=repo.quotas), scope)


def test_concurrent_idempotency_at_capacity(tenant_queue):
    repo, scope, _ = tenant_queue
    repo.quotas = QuotaSettings(True, Limits(1, 1, 1))
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = list(pool.map(lambda _: enqueue(repo, scope, idempotency_key='same'), range(16)))
    assert len({j.id for j in jobs}) == 1
    assert rows(repo, 'quota_admissions') == 1
    with pytest.raises(QuotaExceeded):
        enqueue(repo, scope, idempotency_key='different')
    assert rows(repo, 'durable_jobs') == 1


def test_terminal_release_retries_and_lease_recovery(tenant_queue):
    repo, scope, now = tenant_queue
    repo.quotas = QuotaSettings(True, Limits(20, 20, 1))
    job = enqueue(repo, scope, max_attempts=2)
    claimed = repo.claim_next('worker-' + uuid.uuid4().hex)
    assert repo.fail(job.id, claimed.token, retryable=True)
    with pytest.raises(QuotaExceeded):
        enqueue(repo, scope)
    now[0] += 2
    claimed = repo.claim_next('worker-' + uuid.uuid4().hex)
    now[0] += 61
    # Expired running jobs reserve capacity until durable recovery declares terminal.
    with pytest.raises(QuotaExceeded):
        enqueue(repo, scope)
    assert repo.recover_expired() == 1
    assert not repo.complete(job.id, claimed.token, {})
    next_job = enqueue(repo, scope)
    assert repo.cancel(next_job.id, scope=scope)
    last = enqueue(repo, scope)
    claimed = repo.claim_next('worker-' + uuid.uuid4().hex)
    assert claimed.job.id == last.id
    assert repo.complete(last.id, claimed.token, {})
    enqueue(repo, scope)
    assert rows(repo, 'quota_admissions') == 4


def test_utc_year_rollover_and_failed_jobs_still_count(tenant_queue):
    repo, scope, now = tenant_queue
    repo.quotas = QuotaSettings(True, Limits(1, 1, 1))
    job = enqueue(repo, scope)
    assert repo.cancel(job.id, scope=scope)
    with pytest.raises(QuotaExceeded) as denied:
        enqueue(repo, scope)
    assert 1 <= denied.value.retry_after <= 2
    now[0] += 1
    enqueue(repo, scope)
    assert rows(repo, 'quota_admissions') == 2


def test_daily_reset_does_not_reset_month(tenant_queue):
    repo, scope, now = tenant_queue
    now[0] = datetime(2026, 2, 1, tzinfo=timezone.utc).timestamp()
    repo.quotas = QuotaSettings(True, Limits(1, 1, 2))
    job = enqueue(repo, scope)
    repo.cancel(job.id, scope=scope)
    now[0] += 86400
    with pytest.raises(QuotaExceeded):
        enqueue(repo, scope)
    now[0] = datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp()
    enqueue(repo, scope)


def test_scope_validation_and_tenant_isolation(tenant_queue):
    repo, scope, _ = tenant_queue
    b = AuthRepository(repo.database).create_account('other@example.test', 'synthetic')
    other_org = OrganizationRepository(repo.database).default_for_account(b.id)
    repo.quotas = QuotaSettings(True, Limits(1, 1, 1))
    first = enqueue(repo, scope)
    with pytest.raises(JobValueError):
        enqueue(repo, JobScope(b.id, scope.organization_id))
    with pytest.raises(JobValueError):
        enqueue(repo, JobScope(scope.account_id, scope.organization_id, 999999))
    assert repo.get(first.id, scope=JobScope(b.id, other_org.id)) is None
    assert not repo.cancel(first.id, scope=JobScope(b.id, other_org.id))
    enqueue(repo, JobScope(b.id, other_org.id))
    with pytest.raises(JobValueError):
        enqueue(repo, JobScope())
    assert rows(repo, 'quota_admissions') == 2


def test_shared_org_and_account_fallback_overrides(tenant_queue):
    repo, scope, _ = tenant_queue
    b = AuthRepository(repo.database).create_account('member@example.test', 'synthetic')
    with closing(repo.database.connect()) as conn:
        conn.execute("INSERT INTO organization_members(organization_id,account_id,role,created_at) VALUES(?,?,'member','fixture')", (scope.organization_id, b.id))
        conn.commit()
    repo.quotas = QuotaSettings(True, Limits(0, 0, 0), {
        'organization:' + str(scope.organization_id): Limits(1, 1, 1),
        'account:' + str(b.id): Limits(1, 1, 1)})
    enqueue(repo, scope)
    with pytest.raises(QuotaExceeded):
        enqueue(repo, JobScope(b.id, scope.organization_id))
    enqueue(repo, JobScope(b.id))


def test_failure_rolls_back_both_rows(tenant_queue):
    repo, scope, _ = tenant_queue
    with patch('app.quotas.admission.admit', side_effect=RuntimeError('synthetic failure')):
        with pytest.raises(RuntimeError):
            enqueue(repo, scope)
    assert rows(repo, 'durable_jobs') == rows(repo, 'quota_admissions') == 0
    enqueue(repo, scope)


def test_disabled_and_system_connector(tenant_queue):
    repo, scope, _ = tenant_queue
    repo.quotas = QuotaSettings(False, Limits(0, 0, 0))
    for _ in range(3):
        enqueue(repo, scope)
    enqueue(repo, JobScope())
    assert rows(repo, 'quota_admissions') == 3
    repo.quotas = QuotaSettings(True, Limits(0, 0, 0))
    repo.enqueue('connector.sync.v1', {}, scope=JobScope())
    with pytest.raises(QuotaExceeded):
        enqueue(repo, scope)


@pytest.mark.parametrize('kwargs', [{'daily': True}, {'monthly': -1}, {'outstanding': 1.1}, {'daily': 10**12}])
def test_invalid_limits(kwargs):
    with pytest.raises(ValueError, match='Invalid quota configuration'):
        Limits(**kwargs)


@pytest.mark.parametrize('env', [
    {'VALYQON_QUOTAS_ENABLED': 'yes'}, {'VALYQON_QUOTA_DAILY': '-1'},
    {'VALYQON_QUOTA_TENANT_OVERRIDES': '{"organization:1":{"daily":true}}'},
    {'VALYQON_QUOTA_TENANT_OVERRIDES': '{"organization:1":{},"organization:1":{}}'},
    {'VALYQON_QUOTA_TENANT_OVERRIDES': '{"payload:1":{}}'},
    {'VALYQON_QUOTA_TENANT_OVERRIDES': '[]'},
    {'VALYQON_QUOTA_TENANT_OVERRIDES': '{"account:1":{"unknown":2}}'},
])
def test_invalid_environment_redacted(env):
    with patch.dict('os.environ', env, clear=True):
        with pytest.raises(ValueError, match='^Invalid quota configuration.$'):
            load_quota_settings()


def test_configuration_default_and_immutable():
    with patch.dict('os.environ', {}, clear=True):
        assert not load_quota_settings().enabled
    source = {'account:1': Limits()}
    settings = QuotaSettings(True, overrides=source)
    source.clear()
    assert 'account:1' in settings.overrides
    with pytest.raises(TypeError):
        settings.overrides['account:2'] = Limits()


def test_postgresql_tenant_lock_contract():
    conn = MagicMock()
    settings = QuotaSettings(True)
    key = lock(conn, 'postgresql', settings, JobScope(1, 2), 'fixture.work')
    assert key == 'organization:2'
    sql, params = conn.execute.call_args.args
    assert sql == 'SELECT pg_advisory_xact_lock(?)'
    assert -(2**63) <= params[0] < 2**63
    conn.reset_mock()
    lock(conn, 'postgresql', settings, JobScope(3, 2), 'fixture.work')
    assert conn.execute.call_args.args[1] == params


def test_upgrade_eleven_preserves_checksums(tmp_path):
    from app.database import migrations
    db = Database(DatabaseSettings('', tmp_path / 'old.db'))
    with patch.object(migrations, 'MIGRATIONS', MIGRATIONS[:11]):
        db.migrate()
    with closing(db.connect()) as conn:
        before = [tuple(r) for r in conn.execute('SELECT * FROM app_schema_migrations ORDER BY version')]
    db.migrate()
    db.migrate()
    with closing(db.connect()) as conn:
        assert [tuple(r) for r in conn.execute('SELECT * FROM app_schema_migrations WHERE version<=11 ORDER BY version')] == before
        assert conn.execute('SELECT domain FROM app_schema_migrations WHERE version=12').fetchone()[0] == 'quotas'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    db.close()


def test_enable_enforcement_counts_disabled_work(tenant_queue):
    repo, scope, _ = tenant_queue
    repo.quotas = QuotaSettings(False, Limits(1, 1, 1))
    enqueue(repo, scope)
    repo.quotas = QuotaSettings(True, Limits(1, 1, 1))
    with pytest.raises(QuotaExceeded):
        enqueue(repo, scope)


def test_revoked_member_cannot_admit(tenant_queue):
    repo, scope, _ = tenant_queue
    with closing(repo.database.connect()) as conn:
        conn.execute('DELETE FROM organization_members WHERE organization_id=? AND account_id=?', scope.values[:2][::-1])
        conn.commit()
    with pytest.raises(JobValueError):
        enqueue(repo, scope)
    assert rows(repo, 'quota_admissions') == rows(repo, 'durable_jobs') == 0


def test_upgrade_backfills_and_import_preserves_accounting(tmp_path):
    from app.database import migrations
    from app.database.import_sqlite import import_sqlite
    from tests.test_postgresql_foundation import ImportDestinationFixture
    db = Database(DatabaseSettings('', tmp_path / 'legacy.db'))
    with patch.object(migrations, 'MIGRATIONS', MIGRATIONS[:11]):
        db.migrate()
    a = AuthRepository(db).create_account('legacy@example.test', 'synthetic')
    scope = JobScope(a.id)
    with patch('app.quotas.admission.admit'):
        job = JobRepository(db, quotas=QuotaSettings()).enqueue('fixture.work', {}, scope=scope)
    db.migrate()
    repo = JobRepository(db, quotas=QuotaSettings(True, Limits(100, 100, 1)))
    assert rows(repo, 'quota_admissions') == 1
    with pytest.raises(QuotaExceeded):
        enqueue(repo, scope)
    destination = Database(DatabaseSettings('', tmp_path / 'destination.db'))
    destination.migrate()
    try:
        counts = import_sqlite(db.settings.path, ImportDestinationFixture(destination), dry_run=False)
        assert counts['quota_admissions'] == 1
        target = JobRepository(destination, quotas=repo.quotas)
        assert target.get(job.id, scope=scope) is not None
        with pytest.raises(QuotaExceeded):
            enqueue(target, scope)
    finally:
        destination.close()
        db.close()


def test_inactive_account_denied_before_admission(tenant_queue):
    repo, scope, _ = tenant_queue
    with closing(repo.database.connect()) as conn:
        conn.execute('UPDATE auth_accounts SET is_active=0 WHERE id=?', (scope.account_id,))
        conn.commit()
    with pytest.raises(JobValueError):
        enqueue(repo, scope)
    assert rows(repo, 'quota_admissions') == 0


def test_postgresql_quota_sql_translation():
    from app.database.backend import postgres_sql
    compiled = postgres_sql(MIGRATIONS[11].sql)
    assert 'admitted_at BIGINT' in compiled
    assert 'ON DELETE RESTRICT' in compiled
    assert 'ON CONFLICT DO NOTHING' in compiled
    assert 'CAST(organization_id AS TEXT)' in compiled


def test_legacy_import_backfills_accounting(tmp_path):
    from app.database import migrations
    from app.database.import_sqlite import import_sqlite
    from tests.test_postgresql_foundation import ImportDestinationFixture
    db = Database(DatabaseSettings('', tmp_path / 'legacy-import.db'))
    with patch.object(migrations, 'MIGRATIONS', MIGRATIONS[:11]):
        db.migrate()
    a = AuthRepository(db).create_account('legacy-import@example.test', 'synthetic')
    scope = JobScope(a.id)
    with patch('app.quotas.admission.admit'):
        enqueue(JobRepository(db, quotas=QuotaSettings()), scope)
    destination = Database(DatabaseSettings('', tmp_path / 'legacy-destination.db'))
    destination.migrate()
    try:
        counts = import_sqlite(db.settings.path, ImportDestinationFixture(destination), dry_run=False)
        assert 'quota_admissions' not in counts  # Counts describe unchanged source rows.
        target = JobRepository(destination, quotas=QuotaSettings(True, Limits(100, 100, 1)))
        assert rows(target, 'quota_admissions') == 1
        with pytest.raises(QuotaExceeded):
            enqueue(target, scope)
    finally:
        destination.close()
        db.close()


def test_postgresql_scope_authorization_holds_row_proofs():
    repo = JobRepository(MagicMock(backend='postgresql'), quotas=QuotaSettings())
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = (1,)
    repo._validate_scope(conn, JobScope(1, 2, 3))
    assert len(conn.execute.call_args_list) == 3
    assert all(call.args[0].endswith(' FOR SHARE') for call in conn.execute.call_args_list)


def test_cross_process_atomic_admission(tenant_queue):
    import subprocess
    import sys
    repo, scope, _ = tenant_queue
    script = """
import sys
from pathlib import Path
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import JobRepository, JobScope
from app.quotas import QuotaSettings, Limits, QuotaExceeded
db = Database(DatabaseSettings('', Path(sys.argv[1])))
repo = JobRepository(db, quotas=QuotaSettings(True, Limits(100, 100, 3)))
try:
    repo.enqueue('fixture.work', {}, scope=JobScope(int(sys.argv[2]), int(sys.argv[3])))
except QuotaExceeded:
    sys.exit(2)
finally:
    db.close()
"""
    def submit(_):
        return subprocess.run([sys.executable, '-c', script, str(repo.database.settings.path),
                               str(scope.account_id), str(scope.organization_id)],
                              capture_output=True, timeout=30).returncode
    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = list(pool.map(submit, range(8)))
    assert set(codes) == {0, 2}
    assert codes.count(0) == 3
    assert rows(repo, 'durable_jobs') == rows(repo, 'quota_admissions') == 3
