"""Self-contained offline acceptance: no staging fixtures, sockets or existing DBs."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch
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
        expected_calls = [am.ARMEPS_LISTING_URL] if key == KEYS[0] else [tj.LISTING_URL]
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


@pytest.mark.parametrize('duplicate', [False, True])
def test_armenian_observed_pagination_and_duplicates(monkeypatch, duplicate):
    seen = []
    def handle(request):
        seen.append(str(request.url))
        body = html('am_armeps', 1 if duplicate else len(seen))
        if len(seen) == 1:
            body += f'<a class="pg_n" href="{am.ARMEPS_PAGE_TWO_URL}">2</a>'
        return httpx.Response(200, text=body, headers={'content-type': 'text/html'})
    monkeypatch.setattr(am, 'source_client', lambda **kw: source_client(**kw, transport=httpx.MockTransport(handle)))
    result = asyncio.run(am.ArmeniaArmepsSource().fetch(20))
    assert seen == [am.ARMEPS_LISTING_URL, am.ARMEPS_PAGE_TWO_URL]
    assert [n.external_id for n in result] == (['1'] if duplicate else ['1', '2'])


@pytest.mark.parametrize('navigation', [
    '', '<a class="pg_n" href="https://evil.invalid/">2</a>',
    f'<script><a class="pg_n" href="{am.ARMEPS_PAGE_TWO_URL}">2</a></script>',
    f'<a class="pg_n" href="{am.ARMEPS_LISTING_URL}start/3">3</a>',
])
def test_armenian_no_speculative_second_request(monkeypatch, navigation):
    seen = []
    def handle(request):
        seen.append(str(request.url))
        return httpx.Response(200, text=html('am_armeps') + navigation,
                              headers={'content-type': 'text/html'})
    monkeypatch.setattr(am, 'source_client', lambda **kw: source_client(**kw, transport=httpx.MockTransport(handle)))
    assert len(asyncio.run(am.ArmeniaArmepsSource().fetch(20))) == 1
    assert seen == [am.ARMEPS_LISTING_URL]


def test_armenian_conflicting_pages_fail_before_storage(monkeypatch):
    seen = []
    def handle(request):
        seen.append(str(request.url))
        body = html('am_armeps')
        if len(seen) == 1:
            body += f'<a class="pg_n" href="{am.ARMEPS_PAGE_TWO_URL}">2</a>'
        else:
            body = body.replace('AM-1', 'AM-CHANGED')
        return httpx.Response(200, text=body, headers={'content-type': 'text/html'})
    monkeypatch.setattr(am, 'source_client', lambda **kw: source_client(**kw, transport=httpx.MockTransport(handle)))
    store = Mock()
    with pytest.raises(PermanentJobError):
        ConnectorSyncHandler(catalog(KEYS[0], True), store)(context(), payload(KEYS[0]))
    assert len(seen) == 2
    store.upsert_fenced.assert_not_called()


@pytest.mark.parametrize('key', KEYS)
def test_acceptance_worker_repeat_original_search_and_cleanup(monkeypatch, tmp_path, key):
    from scripts.ci_cis_am_tj_live_acceptance import verify
    import tempfile
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    module = am if key == KEYS[0] else tj
    seen = []
    def handle(request):
        seen.append(str(request.url))
        return httpx.Response(200, text=html(key), headers={'content-type': 'text/html'})
    monkeypatch.setattr(module, 'source_client', lambda **kw: source_client(**kw, transport=httpx.MockTransport(handle)))
    result = verify(key)
    assert result['passed'] and result['stored_notices'] == 1
    assert result['original_field_searches'] == 2
    assert result['repeat_inserted'] == 0 and result['repeat_updated'] == 1
    assert result['enqueue_idempotent']
    assert len(seen) == 2
    assert not list(tmp_path.iterdir())  # Connections must close before Windows cleanup.


def test_worker_page_two_transport_failure_is_not_partial_success(monkeypatch, tmp_path):
    from scripts.ci_cis_am_tj_live_acceptance import verify
    import tempfile
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    seen = []
    def handle(request):
        seen.append(str(request.url))
        if str(request.url) == am.ARMEPS_PAGE_TWO_URL:
            return httpx.Response(503, text='private upstream response')
        body = html(KEYS[0]) + f'<a class="pg_n" href="{am.ARMEPS_PAGE_TWO_URL}">2</a>'
        return httpx.Response(200, text=body, headers={'content-type': 'text/html'})
    monkeypatch.setattr(am, 'source_client', lambda **kw: source_client(**kw, transport=httpx.MockTransport(handle)))
    result = verify(KEYS[0])
    assert not result['passed'] and result['attempts'] == 3
    assert result['job_state'] == 'failed'
    assert result['safe_failure_code'] == 'handler_error'
    assert result['source_probe_rows'] == 1  # A later fetch(1) is NOT worker success.
    assert len(result['worker_failures']) == 3
    assert len(seen) == 7  # Three real bounded attempts plus one direct probe.
    assert 'private upstream' not in str(result)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('key', KEYS)
def test_actual_worker_recovers_using_durable_retry_slots(monkeypatch, tmp_path, key):
    from scripts.ci_cis_am_tj_live_acceptance import verify
    import tempfile
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    module = am if key == KEYS[0] else tj
    seen = []
    def handle(request):
        seen.append(str(request.url))
        if len(seen) == 1:
            raise httpx.ReadTimeout('private timeout payload')
        if len(seen) == 2:
            return httpx.Response(503, text='private unavailable payload')
        return httpx.Response(200, text=html(key), headers={'content-type': 'text/html'})
    monkeypatch.setattr(module, 'source_client', lambda **kw: source_client(**kw, transport=httpx.MockTransport(handle)))
    result = verify(key)
    assert result['passed'] and result['worker_attempts'] == 3
    assert result['repeat_attempts'] == 1
    assert result['repeat_updated'] == 1 and len(seen) == 4
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('key', KEYS)
def test_actual_worker_schema_failure_stays_permanent_and_diagnostic(monkeypatch, tmp_path, key):
    from scripts.ci_cis_am_tj_live_acceptance import verify
    import tempfile
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    module = am if key == KEYS[0] else tj
    transport = httpx.MockTransport(lambda request: httpx.Response(
        200, text='<html>private unverified response</html>', headers={'content-type': 'text/html'}))
    monkeypatch.setattr(module, 'source_client', lambda **kw: source_client(**kw, transport=transport))
    result = verify(key)
    assert not result['passed'] and result['attempts'] == 1
    assert result['safe_failure_code'] == 'permanent_failure'
    assert any(item.get('source_reason') == 'listing_schema' for item in result['worker_failures'][0])
    assert 'private unverified' not in str(result)
    assert not list(tmp_path.iterdir())


def test_worker_diagnostic_never_serializes_exception_payloads():
    from scripts.ci_cis_am_tj_live_acceptance import failure_chain
    private = ValueError('private upstream https://user:secret@example.invalid/')
    error = PermanentJobError('private handler message')
    error.__context__ = private
    private.__context__ = error
    result = failure_chain(error)
    assert [item['type'] for item in result] == ['PermanentJobError', 'ValueError']
    assert 'private' not in str(result) and 'secret' not in str(result)


@pytest.mark.parametrize('unsafe', [False, True])
def test_armenian_actual_bounded_dns_chain_does_not_weaken_public_ip(monkeypatch, unsafe):
    import httpcore
    from app.sources.http_transport import PublicIPError
    def handle(request):
        cause = PublicIPError('private address') if unsafe else httpcore.ConnectError('DNS resolution failed')
        raise httpx.ConnectError('private network message') from cause
    monkeypatch.setattr(am, 'source_client', lambda **kw: source_client(**kw, transport=httpx.MockTransport(handle)))
    store = Mock()
    with pytest.raises(PermanentJobError if unsafe else RetryableJobError):
        ConnectorSyncHandler(catalog(KEYS[0], True), store)(context(), payload(KEYS[0]))
    store.upsert_fenced.assert_not_called()


@pytest.mark.parametrize('status', [408, 429, 500, 502, 504])
def test_armenian_http_transient_statuses_keep_worker_retryable(monkeypatch, status):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text='private response'))
    monkeypatch.setattr(am, 'source_client', lambda **kw: source_client(**kw, transport=transport))
    store = Mock()
    with pytest.raises(RetryableJobError):
        ConnectorSyncHandler(catalog(KEYS[0], True), store)(context(), payload(KEYS[0]))
    store.upsert_fenced.assert_not_called()


def test_live_diagnostic_uses_worker_bounded_client(monkeypatch, capsys):
    from scripts import ci_cis_am_live_dom_diagnostic as diagnostic
    from app.sources.http import BoundedClient
    def client(**kwargs):
        assert _policy.get().max_requests == 1
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, text=html(KEYS[0]), headers={'content-type': 'text/html'}))
        result = source_client(**kwargs, transport=transport)
        assert isinstance(result, BoundedClient)
        return result
    monkeypatch.setattr(diagnostic, 'source_client', client)
    assert asyncio.run(diagnostic.run()) == 1  # One offline row cannot satisfy live minimum.
    assert '"accepted": 1' in capsys.readouterr().out


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


def test_tenant_authenticated_discovery_reads_am_tj_persisted_snapshots_without_live_http():
    """Real API route/session/org checks, actual disposable SQLite, no network.

    Fixture announcements are NOT fresh official live evidence; that is an
    independent CI gate in ci_cis_am_tj_live_acceptance.py.
    """
    from tests.test_organization_workflows import OrganizationWorkflowTests
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    from app.sources.opportunities import OpportunityRepository

    helper = OrganizationWorkflowTests()
    with patch('app.jobs.worker.WorkerPool.start', side_effect=AssertionError('Web must not start workers')):
        helper.setUp()
    try:
        helper.as_account(helper.owner)
        # The real company pre-filter must match both notice titles. Its
        # default test keyword is "aluminium", which correctly excludes both.
        profile = helper.profile('CIS procurement acceptance', 'Pump')
        profile['product_keywords'] = ['Pump', 'Насос']
        profile['search_keywords'] = ['Pump', 'Насос']
        created = helper.client.post(helper.base('/companies'), json={
            'name': 'CIS procurement acceptance', 'profile': profile,
        })
        assert created.status_code == 201, created.text
        database = Database(DatabaseSettings('', helper.path))
        database.migrate()
        store = OpportunityRepository(database)
        store.initialize()
        for key, identifier in (('am_armeps', 101), ('tj_eprocurement', 102)):
            normalized = (am.parse_armeps_listing if key == KEYS[0] else tj.parse_tj_listing)(html(key, identifier))
            assert len(normalized) == 1
            assert store.upsert(normalized[0], connector_version(key))
        canonical = catalog()
        registry = SourceRegistry([replace(canonical.registry.get(key), enabled=True) for key in KEYS])
        cat = SourceCatalog(registry, MultiSourceFetcher(registry, concurrency=1))
        runtime = helper.client.app.state.runtime
        runtime.database = database
        runtime.source_catalog = cat
        endpoint = helper.base('/discover/tenders') + '?snapshots=true'
        response = helper.client.post(endpoint)
        assert response.status_code == 200, response.text
        assert response.headers['X-Valyqon-Discovery-Mode'] == 'snapshots'
        items = response.json()['items']
        assert {row['source'] for row in items} == set(KEYS)
        assert len(items) == 2
        assert helper.client.post(endpoint, headers={'Origin': 'https://evil.invalid'}).status_code == 403
        helper.client.cookies.clear()
        assert helper.client.post(endpoint).status_code == 401
        helper.as_account(helper.outsider)
        assert helper.client.post(endpoint).status_code == 403
    finally:
        helper.doCleanups()
