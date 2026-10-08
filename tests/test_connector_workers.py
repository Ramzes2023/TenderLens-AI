"""Production registry/worker/storage paths with deterministic offline transports."""
import asyncio
import json
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.database.backend import Database, PostgresConnection, postgres_sql
from app.database.config import DatabaseSettings
from app.database.migrations import MIGRATIONS
from app.jobs import HandlerRegistry, JobRepository, JobScope, JobService
from app.jobs.worker import ExecutionContext, PermanentJobError, ShutdownResult, Worker, main
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import SourceCatalog, build_source_catalog
from app.sources.http import BoundedClient, ConnectorTransportError, FetchPolicy, bounded_fetch
from app.sources.ingestion import (JOB_TYPE, SYSTEM_SCOPE, ConnectorSyncHandler, ConnectorSyncService,
                                  connector_version, load_max_records, sync_window)
from app.sources.models import TenderNotice
from app.sources.multi import MultiSourceFetcher
from app.sources.opportunities import OpportunityRepository, validate_notice
from app.sources.registry import SourceRegistration, SourceRegistry, SourceRegistryError
from app.sources.snapshots import snapshot_catalog
from app.sources.ted_api import TedApiSource

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


def notice(source='ted', external_id='one', **changes):
    return replace(TenderNotice(source, external_id, 'Public equipment', 'https://ted.europa.eu/en/notice/one/html',
                                published_at='2026-10-08', currency='EUR', initial_price=100), **changes)


class FakeSource:
    def __init__(self, name='ted', rows=None, error=None):
        self.name, self.rows, self.error, self.calls = name, rows if rows is not None else [notice(name)], error, 0

    async def fetch(self, limit=20):
        self.calls += 1
        if self.error:
            raise self.error
        return list(self.rows)


def catalog_for(*sources):
    registry = SourceRegistry(SourceRegistration(source.name, source.name, source) for source in sources)
    return SourceCatalog(registry, MultiSourceFetcher(registry))


@pytest.fixture
def setup(tmp_path):
    database = Database(DatabaseSettings('', tmp_path / 'connectors.db'))
    clock = SimpleNamespace(value=NOW.timestamp())
    jobs = JobRepository(database, clock=lambda: clock.value)
    jobs.initialize()
    store = OpportunityRepository(database)
    store.initialize()
    source = FakeSource()
    catalog = catalog_for(source)
    service = ConnectorSyncService(JobService(jobs), catalog)
    handler = ConnectorSyncHandler(catalog, store)
    registry = HandlerRegistry()
    registry.register(JOB_TYPE, handler)
    yield SimpleNamespace(database=database, jobs=jobs, store=store, source=source, catalog=catalog,
                          service=service, handler=handler, registry=registry, clock=clock)
    database.close()


def enqueue(s, now=NOW):
    return s.service.enqueue('ted', now=now)


def state(s, job):
    return s.jobs.get(job.id, scope=SYSTEM_SCOPE)


def claim(s):
    return s.jobs.claim_next('worker-' + uuid.uuid4().hex, job_types=(JOB_TYPE,))


def run(s):
    return Worker(s.jobs, s.registry, job_types=(JOB_TYPE,)).run_once()


def test_catalog_constructs_without_network_and_ids_are_static(monkeypatch):
    monkeypatch.delenv('SAM_GOV_API_KEY', raising=False)
    monkeypatch.delenv('KZ_GOSZAKUP_API_TOKEN', raising=False)
    settings = MonitoringSettings(False, 600, 20, 5, 30, (), None)
    with patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')), \
         patch('socket.socket.connect', side_effect=AssertionError('No socket')):
        catalog = build_source_catalog(settings)
    assert catalog.registry.keys() == ('eis', 'ted', 'sam_gov', 'uk_fts', 'canada_buys', 'austender',
                                       'nz_gets', 'za_etenders', 'india_cppp', 'kz_goszakup')
    with pytest.raises(SourceRegistryError):
        SourceRegistry([catalog.registry.get('ted')] * 2)


def test_payload_window_and_concurrent_idempotency(setup):
    s = setup
    with ThreadPoolExecutor(max_workers=4) as executor:
        jobs = list(executor.map(lambda _: enqueue(s), range(8)))
    one = jobs[0]
    assert len({job.id for job in jobs}) == 1
    assert one.scope == JobScope()
    assert one.payload == {'schema': 1, 'source_id': 'ted', 'sync_window': '2026-10-08T12Z',
                           'connector_version': 'connector-sync-v1:ted:adapter-r1'}
    assert enqueue(s, NOW + timedelta(hours=1)).id != one.id
    key = json.dumps(['ted', one.payload['sync_window'], one.payload['connector_version']], separators=(',', ':'))
    assert s.jobs.enqueue(JOB_TYPE, one.payload, scope=SYSTEM_SCOPE, idempotency_key=key).id == one.id
    assert sync_window(NOW.astimezone(timezone(timedelta(hours=2)))) == one.payload['sync_window']


@pytest.mark.parametrize('source', ['unknown', '../ted', 'app.sources.ted_api', 'https://evil.invalid', 'x' * 65])
def test_unknown_or_injected_source_fails_closed(setup, source):
    with pytest.raises(PermanentJobError):
        setup.service.enqueue(source, now=NOW)
    assert setup.source.calls == 0


@pytest.mark.parametrize('change', [{'url': 'https://evil.invalid?secret=synthetic'}, {'schema': True},
                                   {'sync_window': 'x' * 200}, {'sync_window': '2026-02-30T12Z'},
                                   {'connector_version': 'dynamic.module'}, {'source_id': '../ted'}, {'source_id': 'unknown'}])
def test_worker_invalid_payload_is_permanent_and_safe(setup, change):
    payload = dict(enqueue(setup).payload, **change)
    job = setup.jobs.enqueue(JOB_TYPE, payload, scope=SYSTEM_SCOPE)
    # Finish the earlier valid job first, then exercise invalid stored payload.
    run(setup)
    run(setup)
    result = state(setup, job)
    assert result.state == 'failed' and result.failure_code == 'permanent_failure'
    assert result.result is None
    assert setup.source.calls == 1


def test_persist_update_dedup_safe_counts_and_source_isolation(setup):
    s = setup
    s.source.rows = [notice(), notice(), notice(external_id='bad', initial_price=float('nan'))]
    one = enqueue(s)
    assert run(s)
    assert state(s, one).result == {'schema': 1, 'source_id': 'ted', 'sync_window': '2026-10-08T12Z',
                                   'fetched_count': 3, 'accepted_count': 1, 'skipped_count': 2,
                                   'inserted_count': 1, 'updated_count': 0}
    s.source.rows = [notice(title='Updated equipment')]
    two = enqueue(s, NOW + timedelta(hours=1))
    assert run(s) and state(s, two).result['updated_count'] == 1
    assert s.store.read('ted')[0].title == 'Updated equipment'
    assert s.store.upsert(notice('uk_fts'), connector_version('uk_fts'))
    with closing(s.database.connect()) as conn:
        assert conn.execute('SELECT COUNT(*) FROM source_opportunities').fetchone()[0] == 2
        rows = conn.execute('SELECT * FROM source_opportunities WHERE source_id=?', ('ted',)).fetchall()
        assert len(rows) == 1 and rows[0]['first_seen'] <= rows[0]['last_seen']
    assert len(json.dumps(state(s, two).result)) < 500
    assert s.service.status(one.id)['state'] == 'succeeded'
    assert s.jobs.get(one.id, scope=JobScope(12345)) is None
    assert not s.jobs.cancel(one.id, scope=JobScope(12345))


def test_partial_storage_failure_retry_is_idempotent(setup):
    s = setup
    s.source.rows = [notice(external_id='one'), notice(external_id='two')]
    job = enqueue(s)
    original = s.store.upsert
    calls = 0
    def fail_second(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.OperationalError('synthetic raw body secret')
        return original(*args)
    with patch.object(s.store, 'upsert', side_effect=fail_second):
        run(s)
    assert state(s, job).state == 'queued' and len(s.store.read('ted')) == 1
    s.clock.value += 2
    run(s)
    result = state(s, job)
    assert result.state == 'succeeded' and len(s.store.read('ted')) == 2
    assert result.result['updated_count'] == 1 and result.result['inserted_count'] == 1
    assert 'secret' not in json.dumps(result.result)


def test_lease_replay_fences_completion_and_keeps_one_record(setup):
    s = setup
    job = enqueue(s)
    stale = claim(s)
    s.handler(ExecutionContext(stale.job, threading.Event()), stale.job.payload)
    s.clock.value += s.jobs.settings.lease_seconds + 1
    current = claim(s)
    assert current and current.job.id == job.id and current.token != stale.token
    assert not s.jobs.complete(stale.job.id, stale.token, {'unsafe': 'stale'})
    result = s.handler(ExecutionContext(current.job, threading.Event()), current.job.payload)
    assert s.jobs.complete(current.job.id, current.token, result)
    assert len(s.store.read('ted')) == 1 and state(s, job).result['updated_count'] == 1


def test_concurrent_claims_share_one_connector_lane_but_other_jobs_run(setup):
    s = setup
    enqueue(s)
    enqueue(s, NOW + timedelta(hours=1))
    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: claim(s), range(2)))
    assert sum(item is not None for item in claims) == 1
    s.jobs.enqueue('fixture.other', {}, scope=SYSTEM_SCOPE)
    assert s.jobs.claim_next('worker-' + uuid.uuid4().hex, job_types=('fixture.other',)).job.job_type == 'fixture.other'


@pytest.mark.parametrize('error,retry', [(TimeoutError('synthetic secret'), True),
    (httpx.ConnectError('synthetic body'), True), (ConnectorTransportError(retryable=True), True),
    (ConnectorTransportError(), False), (ValueError('secret key invalid'), False)])
def test_fetch_failure_taxonomy_and_redaction(setup, error, retry):
    s = setup
    s.source.error = error
    job = enqueue(s)
    run(s)
    stored = state(s, job)
    assert stored.state == ('queued' if retry else 'failed')
    assert stored.result is None and 'secret' not in str(stored)
    if retry:
        s.source.error = None
        s.clock.value += 2
        run(s)
        assert state(s, job).state == 'succeeded'


@pytest.mark.parametrize('status,retry', [(200, None), (401, False), (403, False), (400, False),
                                        (302, False), (408, True), (429, True), (500, True), (503, True)])
def test_actual_ted_transport_status_worker_classification(setup, status, retry):
    s = setup
    s.catalog = catalog_for(TedApiSource())
    s.handler = ConnectorSyncHandler(s.catalog, s.store)
    s.registry = HandlerRegistry()
    s.registry.register(JOB_TYPE, s.handler)
    calls = []
    def transport(request):
        calls.append(request)
        if status == 200:
            return httpx.Response(200, json={'notices': [{'publication-number': 'one', 'notice-title': 'Equipment'}]})
        return httpx.Response(status, text='synthetic secret raw body', headers={'location': 'https://evil.invalid'})
    original = BoundedClient.__init__
    def init(client, **kwargs):
        return original(client, **dict(kwargs, transport=httpx.MockTransport(transport)))
    job = enqueue(s)
    with patch.object(BoundedClient, '__init__', init):
        run(s)
    assert len(calls) == 1 and calls[0].url.host == 'api.ted.europa.eu'
    assert state(s, job).state == ('succeeded' if retry is None else 'queued' if retry else 'failed')
    assert 'secret' not in json.dumps(state(s, job).result)


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'http://api.ted.europa.eu', 'https://127.0.0.1',
                                'https://api.ted.europa.eu@evil.invalid', 'https://api.ted.europa.eu:444',
                                'https://evil.invalid'])
def test_worker_endpoint_allowlist_blocks_before_transport(url):
    called = []
    async def run_test():
        with bounded_fetch(FetchPolicy(frozenset({'api.ted.europa.eu'}), 1)):
            async with BoundedClient(transport=httpx.MockTransport(lambda request: called.append(request))) as client:
                with pytest.raises(ConnectorTransportError):
                    await client.get(url)
    asyncio.run(run_test())
    assert not called


def test_stream_body_and_request_bounds_are_enforced():
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'1234'
            yield b'5678'
    async def run_test():
        with bounded_fetch(FetchPolicy(frozenset({'api.ted.europa.eu'}), 1, max_bytes=5)):
            async with BoundedClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=Stream()))) as client:
                with pytest.raises(ConnectorTransportError):
                    await client.get('https://api.ted.europa.eu')
                with pytest.raises(ConnectorTransportError):
                    await client.get('https://api.ted.europa.eu')
    asyncio.run(run_test())


@pytest.mark.parametrize('changes', [{'external_id': ''}, {'source': ''}, {'url': 'file:///x'},
    {'title': 'x' * 1001}, {'currency': 'BAD!'}, {'deadline': 'invalid'}, {'initial_price': float('inf')},
    {'summary': '<html>raw</html>'}, {'url': 'https://ted.europa.eu?api_key=synthetic'}])
def test_normalized_validation(changes):
    with pytest.raises(ValueError):
        validate_notice(notice(**changes), 'ted')


def test_snapshots_catalog_never_fetches_live_and_filters_profile_terms(setup):
    s = setup
    s.store.upsert(notice(), connector_version('ted'))
    s.store.upsert(notice(external_id='two', title='Road paving'), connector_version('ted'))
    s.source.error = AssertionError('No live calls')
    snapshot = snapshot_catalog(s.catalog, s.store)
    report = asyncio.run(snapshot.fetch(limit_per_source=20))
    assert len(report.notices) == 2 and not report.failures
    # EIS is the catalog's established keyword-aware route.
    eis = FakeSource('eis')
    s.store.upsert(notice('eis'), connector_version('eis'))
    snapshot = snapshot_catalog(catalog_for(eis), s.store)
    assert len(asyncio.run(snapshot.fetch(search_terms=('equipment',))).notices) == 1
    assert not asyncio.run(snapshot.fetch(search_terms=('unmatched',))).notices
    assert s.source.calls == 0 and eis.calls == 0


def test_result_bound_and_tenant_scope_are_permanent(setup):
    s = setup
    job = enqueue(s)
    s.source.rows = [notice(external_id=str(i)) for i in range(21)]
    run(s)
    assert state(s, job).state == 'failed' and not s.store.read('ted')
    with pytest.raises(PermanentJobError):
        s.handler(ExecutionContext(replace(job, scope=JobScope(1)), threading.Event()), job.payload)


def test_connector_cli_registers_and_executes_real_handler(setup):
    s = setup
    job = enqueue(s)
    class Pool:
        def __init__(self, repository, registry):
            self.registry = registry
            assert isinstance(registry.resolve(JOB_TYPE), ConnectorSyncHandler)
        def start(self):
            assert Worker(s.jobs, self.registry, job_types=self.registry.job_types).run_once()
        def stop(self):
            return ShutdownResult(True, 0)
    with patch('app.database.config.load_database_settings', return_value=s.database.settings), \
         patch('app.sources.catalog.build_source_catalog', return_value=s.catalog), \
         patch('app.monitoring.config.load_monitoring_settings'), \
         patch('app.jobs.worker.WorkerPool', Pool), \
         patch('signal.signal', side_effect=lambda signum, callback:
               callback(signum, None) if getattr(callback, '__name__', '') == 'request_shutdown' else None):
        assert main(['--connectors']) == 0
    assert state(s, job).state == 'succeeded'


def test_real_operator_enqueue_and_safe_status_cli(setup, capsys):
    from app.sources.enqueue import main as enqueue_main
    s = setup
    with patch('app.database.config.load_database_settings', return_value=s.database.settings), \
         patch('app.sources.catalog.build_source_catalog', return_value=s.catalog), \
         patch('app.monitoring.config.load_monitoring_settings'):
        assert enqueue_main(['--source', 'ted']) == 0
        output = json.loads(capsys.readouterr().out)
        assert set(output) == {'job_id', 'state'}
        assert enqueue_main(['--status', output['job_id']]) == 0
        status = json.loads(capsys.readouterr().out)
        assert set(status) == {'job_id', 'state', 'result', 'failure_code'}
        assert enqueue_main(['--source', 'https://evil.invalid']) == 2
    assert s.source.calls == 0


@pytest.mark.parametrize('flags', [[], ['--unknown'], ['--connectors', '--connectors'], ['--connectors', '--url', 'x']])
def test_cli_refuses_invalid_flags_without_storage(flags):
    with patch.object(Database, 'connect', side_effect=AssertionError('No storage')):
        assert main(flags) == 2


@pytest.mark.parametrize('value', ['0', '101', 'bad'])
def test_record_configuration_bounds(monkeypatch, value):
    monkeypatch.setenv('VALYQON_CONNECTOR_MAX_RECORDS', value)
    with pytest.raises(ValueError):
        load_max_records()


def test_postgres_upsert_sql_and_migration_are_compatible():
    raw = MagicMock()
    raw.execute.return_value.rowcount = 0
    database = MagicMock(backend='postgresql', integrity_error=())
    database.connect.side_effect = lambda: PostgresConnection(database, raw)
    assert not OpportunityRepository(database).upsert(notice(), connector_version('ted'))
    sqls = [call.args[0] for call in raw.execute.call_args_list]
    assert any('ON CONFLICT(source_id,external_id) DO NOTHING' in sql and '%s' in sql for sql in sqls)
    assert any('UPDATE source_opportunities' in sql for sql in sqls)
    assert raw.commit.call_count == 1
    ddl = postgres_sql(MIGRATIONS[-1].sql, parameters=False)
    assert 'PRIMARY KEY(source_id, external_id)' in ddl and MIGRATIONS[-1].version == 10


@pytest.mark.parametrize('error', [httpx.ReadTimeout('synthetic credential body'), httpx.ConnectError('synthetic raw body')])
def test_actual_adapter_transport_exceptions_retry(setup, error):
    s = setup
    catalog = catalog_for(TedApiSource())
    registry = HandlerRegistry()
    registry.register(JOB_TYPE, ConnectorSyncHandler(catalog, s.store))
    def transport(request):
        raise error
    original = BoundedClient.__init__
    def init(client, **kwargs):
        return original(client, **dict(kwargs, transport=httpx.MockTransport(transport)))
    job = enqueue(s)
    with patch.object(BoundedClient, '__init__', init):
        Worker(s.jobs, registry).run_once()
    assert state(s, job).state == 'queued' and state(s, job).result is None


@pytest.mark.parametrize('source_id', ['india_cppp', 'kz_goszakup', 'eis'])
def test_actual_adapter_page_limit(setup, source_id):
    from app.sources.india_cppp import IndiaCpppSource
    from app.sources.kz_goszakup import KazakhstanGoszakupApiSource
    from app.sources.eis_rss import EisRssSource
    from tests.test_india_cppp_source import _page, _row
    s = setup
    sources = {'india_cppp': IndiaCpppSource(),
               'kz_goszakup': KazakhstanGoszakupApiSource('synthetic-operator-token'),
               'eis': EisRssSource(tuple(f'https://zakupki.gov.ru/feed/{i}' for i in range(10)))}
    source = sources[source_id]
    catalog = catalog_for(source)
    service = ConnectorSyncService(JobService(s.jobs), catalog)
    registry = HandlerRegistry()
    registry.register(JOB_TYPE, ConnectorSyncHandler(catalog, s.store))
    calls = []
    def transport(request):
        calls.append(request)
        index = len(calls)
        if source_id == 'india_cppp':
            return httpx.Response(200, content=_page(_row(tender_id=f'ID-{index}', reference=f'REF-{index}'), next_page=True))
        if source_id == 'kz_goszakup':
            return httpx.Response(200, json={'items': [{'id': index, 'name_ru': 'Public equipment'}],
                                             'next_page': f'/trd-buy?page={index+1}'})
        return httpx.Response(200, content=(f'<rss><channel><item><guid>{index}</guid><title>Public equipment</title>'
                              '<link>https://zakupki.gov.ru/tender/1</link></item></channel></rss>').encode())
    original = BoundedClient.__init__
    def init(client, **kwargs):
        return original(client, **dict(kwargs, transport=httpx.MockTransport(transport)))
    job = service.enqueue(source_id, now=NOW)
    with patch.object(BoundedClient, '__init__', init):
        Worker(s.jobs, registry).run_once()
    assert len(calls) == 5 and state(s, job).state == 'succeeded'
    assert len(s.store.read(source_id)) == 5
    assert 'synthetic-operator-token' not in json.dumps(job.payload)
    assert 'synthetic-operator-token' not in json.dumps(state(s, job).result)


def test_combined_worker_registers_both_explicit_handlers(setup):
    from app.rag.ingestion import JOB_TYPE as RAG_JOB_TYPE
    s = setup
    class Pool:
        def __init__(self, repository, registry):
            assert set(registry.job_types) == {JOB_TYPE, RAG_JOB_TYPE}
            assert isinstance(registry.resolve(JOB_TYPE), ConnectorSyncHandler)
        def start(self):
            pass
        def stop(self):
            return ShutdownResult(True, 0)
    with patch('app.database.config.load_database_settings', return_value=s.database.settings), \
         patch('app.sources.catalog.build_source_catalog', return_value=s.catalog), \
         patch('app.monitoring.config.load_monitoring_settings'), \
         patch('app.rag.config.load_rag_settings', return_value=SimpleNamespace(enabled=True)), \
         patch('app.rag.ingestion.load_ingestion_options', return_value=(MagicMock(), 2)), \
         patch('app.rag.service.RagService'), patch('app.rag.ingestion.RagIngestionService'), \
         patch('app.rag.ingestion.RagIngestionHandler', return_value=MagicMock()), \
         patch('app.jobs.worker.WorkerPool', Pool), \
         patch('signal.signal', side_effect=lambda signum, callback:
               callback(signum, None) if getattr(callback, '__name__', '') == 'request_shutdown' else None):
        assert main(['--rag', '--connectors']) == 0


def test_snapshot_discover_api_auth_csrf_and_live_compatibility(tmp_path):
    from tests.test_organization_workflows import OrganizationWorkflowTests
    helper = OrganizationWorkflowTests()
    with patch('app.jobs.worker.WorkerPool.start', side_effect=AssertionError('Web must not start workers')):
        helper.setUp()
    try:
        helper.as_account(helper.owner)
        helper.create_company('Snapshot company')
        database = Database(DatabaseSettings('', helper.path))
        database.migrate()
        store = OpportunityRepository(database)
        store.upsert(notice(title='Supply of aluminium profile', currency='RUB'), connector_version('ted'))
        runtime = helper.client.app.state.runtime
        runtime.database = database
        source = FakeSource(rows=[notice(title='Supply of aluminium profile', currency='RUB')])
        runtime.source_catalog = catalog_for(source)
        url = helper.base('/discover/tenders')
        snapshot = helper.client.post(url + '?snapshots=true')
        assert snapshot.status_code == 200, snapshot.text
        assert len(snapshot.json()['items']) == 1 and source.calls == 0
        assert snapshot.headers['X-Valyqon-Discovery-Mode'] == 'snapshots'
        assert helper.client.post(url).status_code == 200 and source.calls == 1
        assert helper.client.post(url + '?snapshots=true', headers={'Origin': 'https://evil.invalid'}).status_code == 403
        helper.client.cookies.clear()
        assert helper.client.post(url + '?snapshots=true').status_code == 401
        helper.as_account(helper.outsider)
        assert helper.client.post(url + '?snapshots=true').status_code == 403
    finally:
        helper.doCleanups()
