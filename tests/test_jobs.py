"""Bounded local concurrency and crash fixtures; no external services or customer work."""
import hashlib
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

from app.database.backend import Database, PostgresConnection, postgres_sql
from app.database.config import DatabaseSettings
from app.database.import_sqlite import TABLES, preflight_source, import_sqlite
from app.database.migrations import MIGRATIONS
from app.jobs import HandlerRegistry, JobRepository, JobScope, JobService, JobSettings, JobValueError, load_job_settings
from app.jobs.models import encode_json
from app.jobs.repository import CLAIM_SQL, POSTGRES_CLAIM_SQL, EXPIRED_SQL, retry_delay
from app.jobs.worker import Worker, WorkerPool, RetryableJobError, PermanentJobError, main

SYSTEM = JobScope()


class Clock:
    def __init__(self):
        self.now = 1800000000.0
    def __call__(self):
        return self.now
    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def queue(tmp_path):
    database = Database(DatabaseSettings('', tmp_path / 'jobs.db'))
    clock = Clock()
    repository = JobRepository(database, clock=clock)
    repository.initialize()
    yield repository, clock
    database.close()


def enqueue(repo, **kwargs):
    return repo.enqueue('fixture.work', {'value': 1}, scope=SYSTEM, **kwargs)


def claim(repo):
    return repo.claim_next('worker-' + uuid.uuid4().hex)


def get(repo, job):
    return repo.get(job.id, scope=SYSTEM)


def test_fresh_schema_and_idempotent_migration(queue):
    repo, _ = queue
    job = enqueue(repo)
    repo.initialize()
    with closing(repo.database.connect()) as conn:
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        assert [tuple(r) for r in conn.execute('SELECT version,domain,checksum FROM app_schema_migrations ORDER BY version')] == [(m.version, m.domain, m.checksum) for m in MIGRATIONS]
        indexes = {r[1] for r in conn.execute('PRAGMA index_list(durable_jobs)')}
        assert {'idx_jobs_claim', 'idx_jobs_expired', 'idx_jobs_scope', 'uq_jobs_idempotency'} <= indexes
    assert get(repo, job).state == 'queued'


def test_upgrade_version_eight_preserves_data_and_checksums(tmp_path):
    from app.database import migrations
    db = Database(DatabaseSettings('', tmp_path / 'old.db'))
    with patch.object(migrations, 'MIGRATIONS', MIGRATIONS[:8]):
        db.migrate()
    from app.auth import AuthRepository
    account = AuthRepository(db).create_account('fixture@example.test', 'synthetic-hash')
    with closing(db.connect()) as conn:
        before = [tuple(r) for r in conn.execute('SELECT * FROM app_schema_migrations ORDER BY version')]
    db.migrate()
    db.migrate()
    with closing(db.connect()) as conn:
        assert [tuple(r) for r in conn.execute('SELECT * FROM app_schema_migrations WHERE version<=8 ORDER BY version')] == before
        assert conn.execute('SELECT password_hash FROM auth_accounts WHERE id=?', (account.id,)).fetchone()[0] == 'synthetic-hash'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    db.close()


def test_old_import_source_without_jobs_is_supported(tmp_path):
    from app.database import migrations
    db = Database(DatabaseSettings('', tmp_path / 'old.db'))
    with patch.object(migrations, 'MIGRATIONS', MIGRATIONS[:8]):
        db.migrate()
    with closing(db.connect()) as conn:
        columns, counts = preflight_source(conn)
        assert 'durable_jobs' not in columns and 'durable_jobs' not in counts
    db.close()


def test_import_preserves_jobs_and_lease_state(queue, tmp_path):
    # Existing importer algorithm fixture, explicitly not a real PostgreSQL server.
    from tests.test_postgresql_foundation import ImportDestinationFixture
    repo, _ = queue
    job = enqueue(repo, idempotency_key='synthetic-identity')
    owned = claim(repo)
    destination = Database(DatabaseSettings('', tmp_path / 'dest.db'))
    destination.migrate()
    try:
        counts = import_sqlite(repo.database.settings.path, ImportDestinationFixture(destination), dry_run=False)
        assert 'durable_jobs' in TABLES and counts['durable_jobs'] == 1
        target = JobRepository(destination, clock=repo.clock)
        assert target.complete(job.id, owned.token, {'restored': True})
    finally:
        destination.close()


def test_scope_is_exact_and_relational(queue):
    from app.auth import AuthRepository
    from app.organizations import OrganizationRepository
    repo, _ = queue
    auth = AuthRepository(repo.database)
    a = auth.create_account('one@example.test', 'synthetic')
    b = auth.create_account('two@example.test', 'synthetic')
    org = OrganizationRepository(repo.database).default_for_account(a.id)
    scope = JobScope(a.id, org.id)
    service = JobService(repo)
    job = service.enqueue('fixture.work', {}, scope=scope)
    assert service.get(job.id, scope=scope).scope == scope
    assert service.get(job.id, scope=JobScope(b.id)) is None
    assert service.get(job.id, scope=SYSTEM) is None
    assert not service.cancel(job.id, scope=JobScope(b.id))
    with pytest.raises(JobValueError):
        service.enqueue('fixture.work', {}, scope=JobScope(b.id, org.id))
    with pytest.raises(JobValueError):
        service.enqueue('fixture.work', {}, scope=JobScope(99999))


def test_company_scope_relationship(queue):
    from tests.test_postgresql_foundation import seeded_source
    repo, _ = queue
    a, org, company = seeded_source(repo.database)
    scope = JobScope(a.id, org.id, company.id)
    job = repo.enqueue('fixture.work', {}, scope=scope)
    assert repo.get(job.id, scope=scope).scope == scope
    with pytest.raises(JobValueError):
        repo.enqueue('fixture.work', {}, scope=JobScope(a.id, org.id, 999999))


@pytest.mark.parametrize('value', [b'bytes', object(), float('nan'), float('inf'), {1: 'bad'}, (1, 2), 2**64])
def test_invalid_json(queue, value):
    repo, _ = queue
    with pytest.raises(JobValueError):
        repo.enqueue('fixture.work', value, scope=SYSTEM)


def test_cyclic_deep_wide_and_oversized_json(queue):
    repo, _ = queue
    cycle = []; cycle.append(cycle)
    deep = None
    for _ in range(34):
        deep = [deep]
    for value in (cycle, deep, [None] * 10001, 'x' * (repo.settings.max_payload_bytes + 1), '\ud800'):
        with pytest.raises(JobValueError):
            repo.enqueue('fixture.work', value, scope=SYSTEM)
    job = enqueue(repo)
    owned = claim(repo)
    with pytest.raises(JobValueError):
        repo.complete(job.id, owned.token, 'x' * (repo.settings.max_result_bytes + 1))
    assert get(repo, job).state == 'running'
    assert encode_json({'z': [None, True, 1.25], 'a': 1}, 100) == '{"a":1,"z":[null,true,1.25]}'


def test_concurrent_idempotency_and_scope_type_policy(queue):
    repo, _ = queue
    barrier = threading.Barrier(8)
    def add(_):
        barrier.wait(timeout=3)
        return enqueue(repo, idempotency_key='synthetic secret caller text')
    with ThreadPoolExecutor(max_workers=8) as executor:
        jobs = list(executor.map(add, range(8)))
    assert len({j.id for j in jobs}) == 1
    owned = claim(repo)
    assert enqueue(repo, idempotency_key='synthetic secret caller text').id == owned.job.id
    assert repo.complete(owned.job.id, owned.token, {})
    assert enqueue(repo, idempotency_key='synthetic secret caller text').id == owned.job.id
    assert repo.enqueue('fixture.other', {}, scope=SYSTEM, idempotency_key='synthetic secret caller text').id != owned.job.id
    with closing(repo.database.connect()) as conn:
        row = conn.execute('SELECT idempotency_hash FROM durable_jobs WHERE id=?', (owned.job.id,)).fetchone()
        assert len(row[0]) == 64 and 'secret' not in row[0]


@pytest.mark.parametrize('terminal', ['failed', 'cancelled'])
def test_terminal_identity_can_be_enqueued_again(queue, terminal):
    repo, _ = queue
    first = enqueue(repo, idempotency_key='key')
    if terminal == 'failed':
        owned = claim(repo)
        assert repo.fail(first.id, owned.token)
    else:
        assert repo.cancel(first.id, scope=SYSTEM)
    assert enqueue(repo, idempotency_key='key').id != first.id


def test_priority_delay_and_fifo(queue):
    repo, clock = queue
    first = enqueue(repo)
    clock.advance(.01)
    second = enqueue(repo)
    high = enqueue(repo, priority=10)
    delayed = enqueue(repo, priority=100, available_at=int((clock.now + 10) * 1000000))
    assert [claim(repo).job.id for _ in range(3)] == [high.id, first.id, second.id]
    assert claim(repo) is None
    clock.advance(10)
    assert claim(repo).job.id == delayed.id


def test_concurrent_claim_one_job(queue):
    repo, _ = queue
    enqueue(repo)
    barrier = threading.Barrier(8)
    def take(_):
        barrier.wait(timeout=3)
        return claim(repo)
    with ThreadPoolExecutor(max_workers=8) as executor:
        claims = list(executor.map(take, range(8)))
    assert sum(c is not None for c in claims) == 1


def test_many_jobs_distributed_once(queue):
    repo, _ = queue
    expected = {enqueue(repo).id for _ in range(24)}
    with ThreadPoolExecutor(max_workers=6) as executor:
        claims = list(executor.map(lambda _: claim(repo), range(30)))
    ids = [c.job.id for c in claims if c]
    assert set(ids) == expected and len(ids) == len(expected)


def test_crash_reclaim_and_stale_operations(queue):
    repo, clock = queue
    job = enqueue(repo)
    dead = claim(repo)
    with closing(repo.database.connect()) as conn:
        stored = conn.execute('SELECT lease_token_hash FROM durable_jobs WHERE id=?', (job.id,)).fetchone()[0]
        assert stored != dead.token and stored == hashlib.sha256(dead.token.encode()).hexdigest()
    clock.advance(repo.settings.lease_seconds)
    assert not repo.complete(job.id, dead.token, {'stale': True})
    replacement = claim(repo)
    assert replacement.job.id == job.id and replacement.job.attempt_count == 2
    assert replacement.token != dead.token
    assert not repo.complete(job.id, dead.token, {'stale': True})
    assert not repo.heartbeat(job.id, dead.token)
    assert not repo.fail(job.id, dead.token, retryable=True)
    assert repo.complete(job.id, replacement.token, {'new': True})
    assert get(repo, job).result == {'new': True}


def test_heartbeat_extends_only_live_owner(queue):
    repo, clock = queue
    enqueue(repo)
    owned = claim(repo)
    clock.advance(30)
    assert not repo.heartbeat(owned.job.id, 'incorrect')
    assert repo.heartbeat(owned.job.id, owned.token)
    updated = get(repo, owned.job)
    assert updated.lease_expires_at > owned.job.lease_expires_at
    clock.advance(30)
    assert repo.recover_expired() == 0
    clock.advance(30)
    assert not repo.heartbeat(owned.job.id, owned.token)
    assert repo.recover_expired() == 1


def test_crashes_exhaust_attempts(queue):
    repo, clock = queue
    job = enqueue(repo, max_attempts=2)
    for _ in range(2):
        assert claim(repo) is not None
        clock.advance(repo.settings.lease_seconds)
    assert claim(repo) is None
    assert get(repo, job).state == 'failed'
    assert get(repo, job).failure_code == 'lease_expired'
    assert get(repo, job).attempt_count == 2


def test_retry_availability_and_exhaustion(queue):
    repo, clock = queue
    job = enqueue(repo, max_attempts=3)
    for attempt in range(1, 4):
        owned = claim(repo)
        assert owned.job.attempt_count == attempt
        assert repo.fail(job.id, owned.token, retryable=True)
        assert claim(repo) is None
        if attempt < 3:
            assert get(repo, job).state == 'queued'
            clock.advance(retry_delay(attempt))
    assert get(repo, job).state == 'failed'
    assert retry_delay(20) == 300


@pytest.mark.parametrize('running', [False, True])
def test_cancellation_fences_success(queue, running):
    repo, _ = queue
    job = enqueue(repo)
    owned = claim(repo) if running else None
    assert repo.cancel(job.id, scope=SYSTEM)
    assert not repo.cancel(job.id, scope=SYSTEM)
    if owned:
        assert not repo.complete(job.id, owned.token, {})
        assert not repo.fail(job.id, owned.token)
        assert not repo.heartbeat(job.id, owned.token)
    assert claim(repo) is None
    assert get(repo, job).state == 'cancelled'


def test_terminal_states_never_restart(queue):
    repo, _ = queue
    job = enqueue(repo)
    owned = claim(repo)
    assert repo.complete(job.id, owned.token, {})
    assert not repo.cancel(job.id, scope=SYSTEM)
    assert not repo.complete(job.id, owned.token, {})
    assert not repo.fail(job.id, owned.token, retryable=True)
    assert claim(repo) is None


@pytest.mark.parametrize('failure,expected', [(RetryableJobError, 'queued'), (PermanentJobError, 'failed'), (RuntimeError, 'failed')])
def test_worker_failure_policy_is_redacted(queue, failure, expected):
    repo, _ = queue
    job = enqueue(repo)
    registry = HandlerRegistry()
    def handler(context, payload):
        raise failure('password session reset verification API redis://secret postgresql://secret')
    registry.register('fixture.work', handler)
    assert Worker(repo, registry).run_once()
    result = get(repo, job)
    assert result.state == expected
    assert 'secret' not in repr(result)
    with closing(repo.database.connect()) as conn:
        assert 'secret' not in str(tuple(conn.execute('SELECT * FROM durable_jobs').fetchone()))


def test_unknown_type_and_invalid_result_fail_safely(queue):
    repo, _ = queue
    job = repo.enqueue('os.system', {'command': 'never execute'}, scope=SYSTEM)
    assert Worker(repo, HandlerRegistry()).run_once()
    assert get(repo, job).failure_code == 'unknown_type'
    registry = HandlerRegistry()
    registry.register('fixture.work', lambda context, payload: object())
    invalid = enqueue(repo)
    Worker(repo, registry).run_once()
    assert get(repo, invalid).failure_code == 'invalid_result'


def test_registry_is_explicit_and_freezes():
    registry = HandlerRegistry()
    with pytest.raises(JobValueError):
        registry.register('arbitrary; import path', lambda c, p: None)
    with pytest.raises(ValueError):
        registry.register('fixture.work', 'os.system')
    registry.register('fixture.work', lambda c, p: None)
    with pytest.raises(ValueError):
        registry.register('fixture.work', lambda c, p: None)
    registry.freeze()
    with pytest.raises(ValueError):
        registry.register('fixture.other', lambda c, p: None)


def test_automatic_heartbeat_during_handler(queue):
    repo, clock = queue
    repo.settings = replace(repo.settings, lease_seconds=.6, heartbeat_seconds=.05)
    job = enqueue(repo)
    registry = HandlerRegistry()
    observed = threading.Event()
    original = repo.heartbeat
    def heartbeat(*args):
        result = original(*args)
        observed.set()
        return result
    repo.heartbeat = heartbeat
    def handler(context, payload):
        clock.advance(.3)
        assert observed.wait(2)
        clock.advance(.3)
        assert repo.recover_expired() == 0
        return {'heartbeat': True}
    registry.register('fixture.work', handler)
    Worker(repo, registry).run_once()
    assert get(repo, job).state == 'succeeded'


def test_heartbeat_loss_marks_context_and_preserves_new_result(queue):
    repo, clock = queue
    repo.settings = replace(repo.settings, lease_seconds=.6, heartbeat_seconds=.05)
    job = enqueue(repo)
    registry = HandlerRegistry()
    def handler(context, payload):
        clock.advance(.6)
        replacement = claim(repo)
        assert repo.complete(job.id, replacement.token, {'new': True})
        assert context.lease_lost.wait(2)
        assert context.should_stop
        return {'old': True}
    registry.register('fixture.work', handler)
    Worker(repo, registry).run_once()
    assert get(repo, job).result == {'new': True}


def test_worker_pool_bounded_graceful_timeout_and_no_new_claims(queue):
    repo, _ = queue
    repo.settings = replace(repo.settings, worker_count=2, poll_seconds=.01)
    jobs = [enqueue(repo) for _ in range(3)]
    entered = threading.Barrier(3)
    release = threading.Event()
    registry = HandlerRegistry()
    def handler(context, payload):
        entered.wait(timeout=3)
        assert release.wait(3)
        assert context.shutdown_requested.is_set()
        return {}
    registry.register('fixture.work', handler)
    pool = WorkerPool(repo, registry)
    pool.start(); pool.start()
    try:
        entered.wait(timeout=3)
        assert pool.alive_count == pool.worker_count == 2
        result = pool.stop(timeout=.01)
        assert not result.completed and result.remaining_workers == 2
        assert sum(get(repo, j).state == 'running' for j in jobs) == 2
    finally:
        release.set()
        assert pool.stop(timeout=3).completed
    assert sum(get(repo, j).state == 'queued' for j in jobs) == 1
    assert pool.stop(timeout=0).completed
    with pytest.raises(RuntimeError):
        pool.start()


def test_worker_stop_and_empty_runner_do_not_open_database(queue, capsys):
    repo, _ = queue
    job = enqueue(repo)
    event = threading.Event(); event.set()
    assert not Worker(repo, HandlerRegistry(), stop_event=event).run_once()
    assert get(repo, job).state == 'queued'
    pool = WorkerPool(repo, HandlerRegistry())
    with pytest.raises(RuntimeError, match='No job handlers'):
        pool.start()
    assert pool.stop(0).completed
    with patch.object(Database, 'connect', side_effect=AssertionError('must not connect')):
        assert main() == 2
    assert 'no production job handlers' in capsys.readouterr().out


@pytest.mark.parametrize('policy', [{'worker_count': 33}, {'worker_count': True}, {'poll_seconds': 0}, {'lease_seconds': float('inf')}, {'heartbeat_seconds': 30}, {'default_max_attempts': 21}, {'max_payload_bytes': 1048577}, {'max_result_bytes': 0}, {'shutdown_seconds': float('nan')}])
def test_settings_bounds(policy):
    with pytest.raises(ValueError, match='Invalid job configuration'):
        JobSettings(**policy)


def test_environment_overrides_dotenv_and_redacts(tmp_path, monkeypatch):
    env = tmp_path / 'settings.env'
    env.write_text('VALYQON_WORKER_COUNT=7\nVALYQON_JOB_POLL_SECONDS=.25\n')
    monkeypatch.setenv('VALYQON_WORKER_COUNT', '3')
    monkeypatch.delenv('VALYQON_JOB_POLL_SECONDS', raising=False)
    assert load_job_settings(env).worker_count == 3
    assert load_job_settings(env).poll_seconds == .25
    monkeypatch.setenv('VALYQON_WORKER_COUNT', 'secret')
    with pytest.raises(ValueError) as error:
        load_job_settings(env)
    assert 'secret' not in str(error.value)


def test_postgres_sql_and_transaction_path(queue):
    repo, _ = queue
    job = enqueue(repo)
    sqlite = repo.database
    owned = claim(repo)
    with closing(sqlite.connect()) as conn:
        job_row = dict(conn.execute('SELECT * FROM durable_jobs WHERE id=?', (job.id,)).fetchone())
    raw = MagicMock()
    calls = []
    def execute(sql, params=None):
        calls.append((sql, params))
        cursor = MagicMock(rowcount=1)
        if 'clock_timestamp()' in sql:
            cursor.fetchone.return_value = {'now': int(repo.clock() * 1000000)}
        elif 'lease_expires_at<=' in sql:
            cursor.fetchall.return_value = []
        elif sql.startswith('SELECT *') or sql.startswith('SELECT attempt_count'):
            cursor.fetchone.return_value = job_row
        else:
            cursor.fetchone.return_value = {'id': job.id}
        return cursor
    raw.execute.side_effect = execute
    db = MagicMock(backend='postgresql', integrity_error=())
    db.connect.side_effect = lambda: PostgresConnection(db, raw)
    pg = JobRepository(db)
    assert pg.claim_next('worker-' + uuid.uuid4().hex).job.id == job.id
    assert pg.heartbeat(job.id, owned.token)
    assert pg.complete(job.id, owned.token, {})
    assert pg.fail(job.id, owned.token, retryable=True)
    assert raw.commit.call_count == 4
    sqls = [sql for sql, _ in calls]
    assert any('FOR UPDATE SKIP LOCKED' in sql and 'priority DESC' in sql for sql in sqls)
    assert any('FOR UPDATE SKIP LOCKED' in sql and 'lease_expires_at<=' in sql for sql in sqls)
    assert not any('BEGIN IMMEDIATE' in sql for sql in sqls)
    assert [params for sql, params in calls if 'pg_advisory' in sql] == [(240_003,)]
    assert '%s' in postgres_sql(POSTGRES_CLAIM_SQL)
    assert 'SKIP LOCKED' not in CLAIM_SQL
    ddl = postgres_sql(MIGRATIONS[8].sql, parameters=False)
    assert 'available_at BIGINT' in ddl and 'account_id BIGINT' in ddl
    assert 'WHERE id=%s' in postgres_sql('SELECT id FROM durable_jobs WHERE id=? FOR UPDATE')
    with pytest.raises(JobValueError):
        JobRepository(db, clock=Clock())


def test_historical_migration_checksums_are_frozen():
    expected = {
        1: '869a55ddf4e51fa4a66eada76738135dc96da9b50b38044cd0d91fab4784aac8',
        2: 'fa82664f9e3276c415f90a3b9a44144bfb78b9bf3a6696cda7ff79534139b3d7',
        3: '7bc713cdb6351cb309446fc75cf93bf26067a94f9001a45623bae480a2aa772c',
        4: '783831b1858895aee001aaef5cc7d4ee6a6b9928f9ebc48c142663f1f26c6ad4',
        5: '5c49a617439e17e8dc98d2374b542105423edc3b1b340ee5fd75ac03e3edcec5',
        6: 'a41ec87c07924561225f5f611c360ce5daee140b1525a86f9868008adc2be233',
        7: '0bc6108e7e49e5e52fa32d184f5b922ade827426be5fe45473a7e4a73ac67276',
        8: 'c1aaac0f56f491f25a6761103a95b2b0905b99becadd5843bd1601430661e48e',
    }
    assert {m.version: m.checksum for m in MIGRATIONS[:8]} == expected
    assert MIGRATIONS[8].version == 9 and MIGRATIONS[8].domain == 'jobs'
    assert MIGRATIONS[-1].version == 10 and MIGRATIONS[-1].domain == 'opportunities'


def test_same_identity_separates_tenants(queue):
    from app.auth import AuthRepository
    repo, _ = queue
    auth = AuthRepository(repo.database)
    one = auth.create_account('scope-one@example.test', 'synthetic')
    two = auth.create_account('scope-two@example.test', 'synthetic')
    first = repo.enqueue('fixture.work', {}, scope=JobScope(one.id), idempotency_key='same')
    second = repo.enqueue('fixture.work', {}, scope=JobScope(two.id), idempotency_key='same')
    assert first.id != second.id


def test_cumulative_json_size_is_bounded_before_full_encoding():
    with pytest.raises(JobValueError):
        encode_json(['x' * 1000] * 100, 10000)


@pytest.mark.parametrize('kwargs', [{'priority': 101}, {'priority': True}, {'max_attempts': 0}, {'available_at': -1}, {'idempotency_key': ''}, {'idempotency_key': 'x' * 1025}])
def test_enqueue_policy_bounds(queue, kwargs):
    with pytest.raises(JobValueError):
        enqueue(queue[0], **kwargs)


def test_worker_cancellation_is_cooperative_and_fenced(queue):
    repo, _ = queue
    repo.settings = replace(repo.settings, heartbeat_seconds=.05)
    job = enqueue(repo)
    registry = HandlerRegistry()
    def handler(context, payload):
        assert repo.cancel(job.id, scope=SYSTEM)
        assert context.lease_lost.wait(2)
        assert context.should_stop
        return {'late': True}
    registry.register('fixture.work', handler)
    assert Worker(repo, registry).run_once()
    assert get(repo, job).state == 'cancelled' and get(repo, job).result is None


def test_heartbeat_storage_uncertainty_fails_closed(queue):
    repo, clock = queue
    repo.settings = replace(repo.settings, lease_seconds=.6, heartbeat_seconds=.05)
    job = enqueue(repo)
    registry = HandlerRegistry()
    def handler(context, payload):
        assert context.lease_lost.wait(2)
        return {'unsafe': True}
    registry.register('fixture.work', handler)
    with patch.object(repo, 'heartbeat', side_effect=RuntimeError('synthetic-secret')):
        Worker(repo, registry).run_once()
    assert get(repo, job).state == 'running' and get(repo, job).result is None
    clock.advance(.6)
    assert repo.recover_expired() == 1
    assert get(repo, job).state == 'queued'


def test_graceful_shutdown_waits_for_inflight_success(queue):
    repo, _ = queue
    repo.settings = replace(repo.settings, worker_count=1)
    entered = threading.Event()
    registry = HandlerRegistry()
    job = enqueue(repo)
    def handler(context, payload):
        entered.set()
        assert context.shutdown_requested.wait(2)
        return {'finished': True}
    registry.register('fixture.work', handler)
    pool = WorkerPool(repo, registry)
    pool.start()
    try:
        assert entered.wait(2)
    finally:
        assert pool.stop(3).completed
    assert get(repo, job).state == 'succeeded'


def test_async_handlers_are_rejected():
    async def handler(context, payload):
        return {}
    with pytest.raises(ValueError):
        HandlerRegistry().register('fixture.work', handler)


def test_claim_failure_rolls_back(queue):
    repo, _ = queue
    job = enqueue(repo)
    original = repo.database.connect
    def connect():
        raw = original()
        class Connection:
            def execute(self, sql, params=()):
                if sql.startswith('SELECT *') and 'WHERE id=' in sql:
                    raise RuntimeError('synthetic post-update failure')
                return raw.execute(sql, params)
            def commit(self): raw.commit()
            def rollback(self): raw.rollback()
            def close(self): raw.close()
        return Connection()
    with patch.object(repo.database, 'connect', connect), pytest.raises(RuntimeError):
        claim(repo)
    assert get(repo, job).state == 'queued' and get(repo, job).attempt_count == 0


def test_import_rejects_missing_jobs_after_version_nine(queue):
    repo, _ = queue
    with closing(repo.database.connect()) as conn, conn:
        conn.execute('DROP TABLE durable_jobs')
    with closing(repo.database.connect()) as conn, pytest.raises(Exception, match='job schema is missing'):
        preflight_source(conn)
