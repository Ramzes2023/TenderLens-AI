"""Saved public evidence and existing framework contracts only; no live requests."""
import asyncio
import json
from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs.models import JobScope
from app.jobs.worker import PermanentJobError
from app.monitoring.config import MonitoringSettings
from app.scoring.runs import ScoringInputError, ScoringRunService, validate_configuration
from app.sources import b2b_center
from app.sources.b2b_center import B2BCenterSource, parse_b2b_center_listing
from app.sources.catalog import build_source_catalog
from app.sources.eis_rss import SourceError
from app.sources.http import FetchPolicy, bounded_fetch, ConnectorTransportError
from app.sources.ingestion import ConnectorSyncHandler, SYSTEM_SCOPE, connector_version, validate_payload
from app.sources.models import TenderNotice
from app.sources.multi import MultiSourceFetcher
from app.sources.opportunities import OpportunityRepository, validate_notice
from app.sources.registry import SourceRegistration, SourceRegistry
from app.sources.snapshots import snapshot_catalog

PAYLOAD = (Path(__file__).parent / 'fixtures/ru04/b2b_center.html').read_bytes()


def settings(**changes):
    return replace(MonitoringSettings(False, 600, 20, 5, 30, (), None,
                                      profile_feeds_enabled=False), **changes)


def payload():
    return {'schema': 1, 'source_id': 'b2b_center', 'sync_window': '2026-10-13T12Z',
            'connector_version': connector_version('b2b_center')}


@pytest.fixture
def repository(tmp_path):
    database = Database(DatabaseSettings('', tmp_path / 'ru04.db'))
    store = OpportunityRepository(database)
    store.initialize()
    yield store
    database.close()


def test_saved_evidence_extraction_identity_and_original_reference():
    notices = parse_b2b_center_listing(PAYLOAD)
    assert len(notices) == 10
    assert [n.external_id for n in notices] == sorted(n.external_id for n in notices)
    notice = next(n for n in notices if n.external_id == 'l15289907-3-9-1')
    assert notice.identity == ('b2b_center', 'l15289907-3-9-1')
    assert notice.title == 'Доработка сайта заказчика'
    assert notice.customer == 'ГОСУДАРСТВЕННЫЙ МУЗЕЙ ИСТОРИИ РЕЛИГИИ'
    assert notice.url == 'https://www.b2b-center.ru/search/number/l15289907-3-9-1/'
    assert notice.tender_number == '200909828126100317'
    assert notice.initial_price == 100000 and notice.currency == 'RUB'
    assert notice.published_at == '2026-10-13T17:50:04+03:00'
    assert notice.deadline == '2026-10-13T19:50:00+03:00'
    assert notice.origin == 'aggregated' and notice.upstream_host == 'agregatoreat.ru'
    assert notice.upstream_url.endswith('/eb5ffd56-ca42-4fec-86e8-cd6d55b021db/info')
    assert all(validate_notice(n, 'b2b_center') is n for n in notices)
    assert parse_b2b_center_listing(PAYLOAD + PAYLOAD) == notices
    assert parse_b2b_center_listing(PAYLOAD, limit=2) == notices[:2]


@pytest.mark.parametrize('raw', [b'', b'<html><script>app()</script></html>',
                                b'<html>CAPTCHA login</html>', b'<div class="cards">broken',
                                b'\xff', b'x' * (b2b_center.MAX_BYTES + 1)],
                         # Pytest exports the node ID via PYTEST_CURRENT_TEST;
                         # keep it bounded even for the oversized HTML case.
                         ids=['empty', 'script-only', 'captcha-login', 'broken-card',
                              'invalid-utf8', 'oversized'])
def test_unusable_html_fails_closed(raw):
    with pytest.raises(SourceError):
        parse_b2b_center_listing(raw)


@pytest.mark.parametrize('replacement', [
    b'https://evil.example/search/number/l15289907-3-9-1/',
    b'https://www.b2b-center.ru.evil.example/search/number/l15289907-3-9-1/',
    b'https://user@www.b2b-center.ru/search/number/l15289907-3-9-1/',
    b'https://www.b2b-center.ru:444/search/number/l15289907-3-9-1/',
    b'//www.b2b-center.ru/search/number/l15289907-3-9-1/',
    b'https://www.b2b-center.ru/search/number/l15289907-3-9-1/?token=x',
    b'https://www.b2b-center.ru/search/number/l15289907-3-9-1/#fragment',
    b'https://www.b2b-center.ru/search/number/../',
])
def test_detail_host_and_path_validation(replacement):
    original = b'https://www.b2b-center.ru/search/number/l15289907-3-9-1/'
    with pytest.raises(SourceError):
        parse_b2b_center_listing(PAYLOAD.replace(original, replacement))


def test_unknown_optional_attributes_and_conflicting_duplicate():
    changed = PAYLOAD.replace(b'itemprop="priceCurrency"', b'itemprop="unknownCurrency"')
    notices = parse_b2b_center_listing(changed)
    assert all(n.initial_price is None and n.currency is None for n in notices)
    # Unknown markup does not manufacture publication dates or currencies.
    changed = changed.replace(b'itemprop="validFrom"', b'itemprop="unknownDate"')
    assert all(n.published_at is None for n in parse_b2b_center_listing(changed))
    with pytest.raises(SourceError):
        parse_b2b_center_listing(PAYLOAD + PAYLOAD.replace(b'100000.00', b'100001.00'))


def test_default_off_explicit_catalog_and_eis_unchanged():
    default = build_source_catalog(settings())
    active = build_source_catalog(settings(b2b_center_enabled=True))
    assert 'b2b_center' not in default.registry.keys()
    assert 'roseltorg' not in active.registry.keys()
    assert active.enabled_keys == (*default.enabled_keys, 'b2b_center')
    assert active.registry.get('eis') == default.registry.get('eis')
    assert active.registry.get('b2b_center').official is False
    with pytest.raises(PermanentJobError):
        validate_payload(payload(), default.registry)
    assert validate_payload(payload(), active.registry).key == 'b2b_center'
    assert validate_configuration(['b2b_center'], 20)['sources'] == ['b2b_center']
    with pytest.raises(ScoringInputError):
        ScoringRunService(SimpleNamespace(repository=SimpleNamespace(database=None)),
                          catalog=default).enqueue(scope=JobScope(), sources=['b2b_center'])
    enabled223 = settings(eis_223_enabled=True,
                          eis_223_rss_urls=('https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?fz223=on',))
    before, after = build_source_catalog(enabled223), build_source_catalog(replace(enabled223, b2b_center_enabled=True))
    assert before.registry.get('eis_223') == after.registry.get('eis_223')


def mock_transport(monkeypatch, status=200, headers=None):
    calls = []
    original = b2b_center.source_client
    def factory(**kwargs):
        def respond(request):
            calls.append(str(request.url))
            return httpx.Response(status, content=PAYLOAD, headers=headers)
        return original(**kwargs, transport=httpx.MockTransport(respond))
    monkeypatch.setattr(b2b_center, 'source_client', factory)
    return calls


def test_bounded_transport_budget_and_host_isolation(monkeypatch):
    calls = mock_transport(monkeypatch)
    policy = FetchPolicy(b2b_center.B2B_CENTER_HOSTS, 1)
    async def run():
        with bounded_fetch(policy):
            assert len(await B2BCenterSource().fetch(3)) == 3
            with pytest.raises(ConnectorTransportError):
                await B2BCenterSource().fetch(3)
        with bounded_fetch(FetchPolicy(frozenset({'zakupki.gov.ru'}), 1)):
            with pytest.raises(ConnectorTransportError):
                await B2BCenterSource().fetch()
    asyncio.run(run())
    assert calls == [b2b_center.B2B_CENTER_LIST_URL]
    assert policy.requests == 1


def test_redirect_never_follows_upstream(monkeypatch):
    calls = mock_transport(monkeypatch, 302, {'Location': 'https://evil.example/'})
    with pytest.raises(ConnectorTransportError):
        asyncio.run(B2BCenterSource().fetch())
    assert calls == [b2b_center.B2B_CENTER_LIST_URL]


def test_worker_repository_offline_discovery_contract(monkeypatch, repository):
    calls = mock_transport(monkeypatch)
    catalog = build_source_catalog(settings(b2b_center_enabled=True))
    handler = ConnectorSyncHandler(catalog, repository, max_records=3)
    context = SimpleNamespace(job=SimpleNamespace(scope=SYSTEM_SCOPE), should_stop=False)
    result = handler(context, payload())
    assert result['accepted_count'] == result['inserted_count'] == 3
    assert handler(context, payload())['updated_count'] == 3
    assert len(calls) == 2
    stored = repository.read('b2b_center')
    assert len(stored) == 3 and not repository.read('roseltorg')
    with closing(repository.database.connect()) as conn:
        row = conn.execute('SELECT notice_json FROM source_opportunities WHERE source_id=? LIMIT 1',
                           ('b2b_center',)).fetchone()
    assert 'upstream_url' in json.loads(row[0])
    assert all('upstream_url' in json.loads(n.summary) for n in stored)
    def forbidden(**kwargs):
        pytest.fail('Snapshot discovery must never use HTTP')
    monkeypatch.setattr(b2b_center, 'source_client', forbidden)
    report = asyncio.run(snapshot_catalog(catalog, repository).fetch(source_keys=['b2b_center']))
    assert len(report.notices) == 3 and report.healthy
    empty = asyncio.run(snapshot_catalog(catalog, repository).fetch(
        source_keys=['b2b_center'], search_terms=['ru04-no-match-synthetic-keyword']))
    assert empty.healthy and not empty.notices
    assert all(set(asdict(n)) == set(asdict(TenderNotice('x', 'x', 'x', 'https://x.test/')))
               for n in report.notices)
    private = SimpleNamespace(job=SimpleNamespace(scope=JobScope(1, 2, 3)),
                              should_stop=False)
    with pytest.raises(PermanentJobError):
        handler(private, payload())


def test_100_synthetic_sources_capacity_and_failure_isolation():
    active, peak = 0, 0
    class Fake:
        def __init__(self, name):
            self.name = name
        async def fetch(self, limit=20):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0)
                if self.name == 'fake_099':
                    raise SourceError('Synthetic failure')
                n = TenderNotice(self.name, 'one', 'Synthetic', 'https://example.test/one')
                return [n, n]
            finally:
                active -= 1
    registry = SourceRegistry(SourceRegistration(f'fake_{i:03}', 'Synthetic capacity source',
                                                 Fake(f'fake_{i:03}')) for i in range(100))
    report = asyncio.run(MultiSourceFetcher(registry, concurrency=8).fetch())
    assert len(report.attempted_sources) == len(report.statuses) == 100
    assert len(report.notices) == 99 and len(report.failures) == 1
    assert report.partial_failure and peak <= 8
    assert tuple(n.source for n in report.notices) == registry.keys()[:-1]
