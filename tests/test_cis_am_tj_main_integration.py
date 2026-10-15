"""Self-contained offline acceptance: no staging fixtures, sockets or existing DBs."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
import socket
from contextvars import ContextVar
import ssl

import httpx
import pytest
from app.monitoring.config import MonitoringSettings
from app.sources import am_armeps as am, tj_eprocurement as tj
from app.sources.catalog import build_source_catalog, SourceCatalog
from app.sources.http import source_client, _policy, bounded_fetch, FetchPolicy
from app.sources.ingestion import (ConnectorSyncHandler, ConnectorSyncService, SYSTEM_SCOPE,
                                  connector_version, HOSTS)
from app.sources.multi import MultiSourceFetcher
from app.sources.registry import SourceRegistry
from app.jobs.worker import PermanentJobError, RetryableJobError

KEYS = ('am_armeps', 'tj_eprocurement')

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def reject(*args, **kwargs):
        raise AssertionError('Network forbidden in offline acceptance')
    original_connect, original_pair = socket.socket.connect, socket.socketpair
    internal_pair = ContextVar('internal_pair', default=False)
    def pair(*args, **kwargs):
        token = internal_pair.set(True)
        try:
            return original_pair(*args, **kwargs)
        finally:
            internal_pair.reset(token)
    def connect(sock, address):
        if internal_pair.get() and address[0] in {'127.0.0.1', '::1'}:
            return original_connect(sock, address)
        return reject()
    monkeypatch.setattr(socket, 'socketpair', pair)
    monkeypatch.setattr(socket.socket, 'connect', connect)
    monkeypatch.setattr(socket, 'getaddrinfo', reject)
    for key in ('SAM_GOV_API_KEY', 'KZ_GOSZAKUP_API_TOKEN'):
        monkeypatch.delenv(key, raising=False)


def catalog(key=None, enabled=False):
    settings = MonitoringSettings(False, 600, 20, 5, 10, (), None,
        eis_223_enabled=True, eis_223_profile_feeds_enabled=True,
        b2b_center_enabled=True)
    cat = build_source_catalog(settings)
    if key:
        registry = SourceRegistry([replace(cat.registry.get(key), enabled=enabled)])
        return SourceCatalog(registry, MultiSourceFetcher(registry))
    return cat


def html(key, identifier=1):
    if key == 'am_armeps':
        headers = ['ID', 'Code', 'Title', 'Lots count', 'Status', 'End bid time', '']
        cells = [str(identifier), 'AM-1', 'Pump Պոմպ', '1', 'Open', '2026-12-01 10:00:00',
                 f'<a href="https://eauction.armeps.am/en/public/tender_details/tid/{identifier}/"></a>']
    else:
        headers = tj.HEADERS
        cells = ['1', 'Organizer', 'Customer',
                 f'<a href="/ru/announce/index/{identifier}">Насос Таҷҳизот</a>',
                 'Open', 'Goods', '2026-10-01 10:00:00', '2026-12-01 10:00:00', '1', 'Open']
    return '<table><tr>' + ''.join(f'<th>{v}</th>' for v in headers) + '</tr><tr>' + ''.join(f'<td>{v}</td>' for v in cells) + '</tr></table>'


def payload(key):
    return dict(schema=1, source_id=key, sync_window='2026-10-15T12Z',
                connector_version=connector_version(key))


def context():
    return SimpleNamespace(job=SimpleNamespace(scope=SYSTEM_SCOPE), should_stop=False)


def test_defaults_preserve_main():
    cat = catalog()
    assert {'world_bank', 'eis', 'eis_223', 'b2b_center', 'ted'} <= set(cat.enabled_keys)
    assert {'world_bank', 'eis_223', 'b2b_center'} <= set(HOSTS)
    for key in KEYS:
        reg = cat.registry.get(key)
        assert not reg.enabled and reg.official
        assert not reg.capabilities.keyword_search and not reg.capabilities.documents
        jobs = Mock()
        with pytest.raises(PermanentJobError):
            ConnectorSyncService(jobs, cat).enqueue(key)
        jobs.enqueue.assert_not_called()
        report = asyncio.run(cat.fetch(source_keys=[key]))
        assert not report.attempted_sources


@pytest.mark.parametrize('key', KEYS)
def test_actual_ingestion_budget_and_provenance(monkeypatch, tmp_path, key):
    # The HTTP transport is mocked; the job lease, database transactions,
    # opportunity persistence and saved-search snapshot are all REAL.
    import threading
    import uuid
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    from app.jobs import JobRepository, JobService
    from app.jobs.worker import ExecutionContext
    from app.sources.opportunities import OpportunityRepository
    from app.sources.snapshots import snapshot_catalog
    from app.sources.ingestion import JOB_TYPE
    module = am if key == KEYS[0] else tj
    calls = []
    def handle(request):
        calls.append(str(request.url))
        policy = _policy.get()
        assert policy.hosts == HOSTS[key]
        assert policy.max_requests == (2 if key == KEYS[0] else 1)
        return httpx.Response(200, text=html(key, len(calls)), headers={'content-type': 'text/html'})
    monkeypatch.setattr(module, 'source_client', lambda **kw: source_client(**kw, transport=httpx.MockTransport(handle)))
    cat = catalog(key, True)
    database = Database(DatabaseSettings('', tmp_path / (key + '.db')))
    jobs = JobRepository(database)
    jobs.initialize()
    store = OpportunityRepository(database)
    store.initialize()
    try:
        queued = ConnectorSyncService(JobService(jobs), cat).enqueue(key)
        claim = jobs.claim_next('worker-' + uuid.uuid4().hex, job_types=(JOB_TYPE,))
        assert claim is not None and claim.job.id == queued.id
        ctx = ExecutionContext(claim.job, threading.Event())
        ctx.fenced_write = lambda write: jobs.fenced_write(claim.job.id, claim.token, write)
        result = ConnectorSyncHandler(cat, store, max_records=100)(ctx, claim.job.payload)
        assert jobs.complete(claim.job.id, claim.token, result)
        expected_calls = [am.ARMEPS_LISTING_URL, am.ARMEPS_PAGE_TWO_URL] if key == KEYS[0] else [tj.LISTING_URL]
        assert calls == expected_calls
        assert result['accepted_count'] == len(calls)
        rows = store.read(key, 100)
        assert len(rows) == len(calls)
        assert len({n.identity for n in rows}) == len(rows)
        assert all(n.source == key for n in rows)
        term = 'Պոմպ' if key == KEYS[0] else 'Таҷҳизот'
        report = asyncio.run(snapshot_catalog(cat, store).fetch(source_keys=[key], search_terms=(term,), limit_per_source=100))
        assert len(report.notices) == len(rows)
        assert not report.failures
        assert _policy.get() is None
    finally:
        database.close()


@pytest.mark.parametrize('key', KEYS)
@pytest.mark.parametrize('failure', ['timeout', 'tls', 'unknown', 'redirect', 'server', 'parse'])
def test_transport_and_parser_fail_closed(monkeypatch, key, failure):
    module = am if key == KEYS[0] else tj
    def handle(request):
        if failure == 'timeout':
            raise httpx.ReadTimeout('sensitive', request=request)
        if failure == 'tls':
            raise httpx.ConnectError('sensitive') from ssl.SSLCertVerificationError('sensitive')
        if failure == 'unknown':
            raise httpx.ConnectError('sensitive')
        return httpx.Response(503 if failure == 'server' else 302 if failure == 'redirect' else 200,
                              text='<html>changed</html>', headers={'content-type': 'text/html', 'location': 'https://evil.invalid'})
    monkeypatch.setattr(module, 'source_client', lambda **kw: source_client(**kw, transport=httpx.MockTransport(handle)))
    store = Mock()
    expected = RetryableJobError if failure in {'timeout', 'server'} else PermanentJobError
    with pytest.raises(expected) as caught:
        ConnectorSyncHandler(catalog(key, True), store)(context(), payload(key))
    assert 'sensitive' not in str(caught.value)
    store.upsert_fenced.assert_not_called()
    store.upsert.assert_not_called()
    assert _policy.get() is None


@pytest.mark.parametrize('key', KEYS)
@pytest.mark.parametrize('change', [{'schema': True}, {'url': 'https://evil.invalid'},
                                   {'connector_version': 'old'}, {'sync_window': '2026-02-30T12Z'}])
def test_payload_validation(key, change):
    store = Mock()
    with pytest.raises(PermanentJobError):
        ConnectorSyncHandler(catalog(key, True), store)(context(), dict(payload(key), **change))
    store.upsert_fenced.assert_not_called()
    store.upsert.assert_not_called()


@pytest.mark.parametrize('key', KEYS)
def test_parser_rejects_host_injection_and_oversize(key):
    parse = am.parse_armeps_listing if key == KEYS[0] else tj.parse_tj_listing
    good = html(key)
    assert len(parse(good)) == 1
    bad = good.replace('https://eauction.armeps.am', 'https://evil.invalid') if key == KEYS[0] else good.replace('/ru/announce/index/', 'https://evil.invalid/ru/announce/index/')
    for value in (bad, 'x' * (1024 * 1024 + 1), '<table></table>'):
        with pytest.raises(am.SourceError):
            parse(value)


@pytest.mark.parametrize('key', KEYS)
def test_enclosing_policy_is_not_broadened(monkeypatch, key):
    module = am if key == KEYS[0] else tj
    transport = httpx.MockTransport(lambda request: pytest.fail('must reject before dispatch'))
    monkeypatch.setattr(module, 'source_client', lambda **kw: source_client(**kw, transport=transport))
    async def run():
        with bounded_fetch(FetchPolicy(frozenset({'example.invalid'}), 1)):
            with pytest.raises(am.SourceError):
                await catalog(key, True).registry.get(key).source.fetch()
    asyncio.run(run())
    assert _policy.get() is None

@pytest.mark.parametrize('key', KEYS)
def test_saved_keyword_search_is_request_local(key):
    from app.sources.snapshots import snapshot_catalog
    repo = Mock()
    repo.read.return_value = []
    cat = snapshot_catalog(catalog(key, True), repo)
    asyncio.run(cat.fetch(source_keys=[key], limit_per_source=1, search_terms=('НАСОС', 'Պոմպ', 'Таҷҳизот')))
    repo.read.assert_called_once_with(key, 1, ('НАСОС', 'Պոմպ', 'Таҷҳизот'))
    assert cat.registry.get(key).source.terms == ()
    repo.reset_mock()
    asyncio.run(cat.fetch(source_keys=[key], limit_per_source=2))
    repo.read.assert_called_once_with(key, 2, ())
