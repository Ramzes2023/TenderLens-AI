"""RU-08 captured evidence and isolated integration; no live requests in pytest."""
import asyncio
from contextlib import closing
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.monitoring.config import MonitoringSettings
from app.sources.b2b_center import parse_b2b_center_listing
from app.sources.catalog import SourceCatalog
from app.sources.eis_rss import SourceError
from app.sources.eis_223_rss import parse_eis_223_feed
from app.sources.http import _policy, _validate_bounded_url, FetchPolicy, ConnectorTransportError
from app.sources.multi import MultiSourceFetcher
from app.sources.opportunities import OpportunityRepository
from app.sources.registry import SourceRegistry
from app.sources.ru08_integration import (
    local_catalog, SOURCE_KEYS, HOSTS, LocalBoundedSource, duplicate_diagnostics, save_and_query)

FIXTURES = Path(__file__).with_name('fixtures') / 'ru08'
CAPTURE_HASH = 'b5ec85c85e9a29ff2fd02a6815adbdcdc61ca2155d34fb8c18e057325d945aa7'
# Git normalizes the captured response's mixed CRLF/LF line endings.
# Keep the original 246338-byte host-capture digest above; separately pin
# the canonical 243045-byte Git checkout rather than pretending it is raw.
REPOSITORY_NORMALIZED_CAPTURE_HASH = '1f937626a85fffdb99de5bb7db10fc99a5a6a41407cc53a53e04c35c0565fc7d'


def captured_records():
    payload = (FIXTURES / 'b2b_search.html').read_bytes()
    assert (hashlib.sha256(payload).hexdigest() == CAPTURE_HASH
            or hashlib.sha256(payload.replace(b'\r\n', b'\n')).hexdigest()
            == REPOSITORY_NORMALIZED_CAPTURE_HASH)
    return parse_b2b_center_listing(payload, limit=100)


def test_real_capture_identifiers_urls_and_eis_references():
    records = captured_records()
    assert len(records) == 10
    assert len({notice.identity for notice in records}) == 10
    assert {'l4639392-4-12-1', 'l0338200012226000019-1'} <= {n.external_id for n in records}
    assert all(n.url == 'https://www.b2b-center.ru/search/number/' + n.external_id + '/' for n in records)
    diagnostics = duplicate_diagnostics(records)
    assert set(diagnostics['eis_references']) == {
        '0338200012226000019', '0348200072726000025', '0358100010326000043'}
    assert diagnostics['cross_source_links'] == {}  # No fetched EIS counterpart in this capture.


def test_real_capture_fetch_registry_upsert_and_user_snapshot_query(tmp_path):
    class CapturedSource:
        name = 'b2b_center'

        async def fetch(self, limit=20):
            return captured_records()[:limit]

    catalog = local_catalog(enable_b2b=True)
    registry = SourceRegistry(replace(item, source=CapturedSource()) if item.key == 'b2b_center'
                              else item for item in catalog.registry.registrations())
    catalog = SourceCatalog(registry, MultiSourceFetcher(registry, concurrency=1))
    database = Database(DatabaseSettings('ru08-test-only', tmp_path / 'public.sqlite'))
    repository = OpportunityRepository(database)
    repository.initialize()
    report = asyncio.run(catalog.fetch(source_keys=('b2b_center',), limit_per_source=20))
    assert not report.failures
    counts = asyncio.run(save_and_query(catalog, repository, 'b2b_center', report.notices))
    assert counts == (10, 10)
    assert asyncio.run(save_and_query(catalog, repository, 'b2b_center', report.notices)) == (10, 10)
    assert len(repository.read('b2b_center', limit=100)) == 10  # Idempotent per-source key.
    assert repository.read('b2b_center', search_terms=('RU08_IMPOSSIBLE_QUERY_7fb92',)) == []
    with closing(database.connect()) as conn:
        row = conn.execute('SELECT notice_json,connector_version FROM source_opportunities WHERE external_id=?',
                           ('l0338200012226000019-1',)).fetchone()
    assert 'zakupki.gov.ru' in json.loads(row[0])['upstream_url']
    assert row[1] == 'connector-sync-v1:b2b_center:adapter-r1'


def test_six_diagnostic_entries_and_opt_in_defaults():
    settings = MonitoringSettings(False, 600, 20, 5, 15, (), None)
    assert not settings.eis_223_enabled and not settings.b2b_center_enabled
    catalog = local_catalog()
    assert set(catalog.registry.keys()) == set(SOURCE_KEYS.values())
    assert catalog.enabled_keys == ('eis',)
    enabled = local_catalog(enable_eis223=True, enable_b2b=True)
    assert set(enabled.enabled_keys) == {'eis', 'eis_223', 'b2b_center'}
    for key in ('eis', 'eis_223'):
        source = enabled.registry.get(key).source.source
        query = parse_qs(urlsplit(source.urls[0]).query)
        assert query['fz44' if key == 'eis' else 'fz223'] == ['on']
    for key in ('tektorg', 'roseltorg', 'fabrikant'):
        assert not enabled.registry.get(key).enabled
        with pytest.raises(SourceError):
            asyncio.run(enabled.registry.get(key).source.fetch())


@pytest.mark.parametrize('label', ['login', 'captcha', 'bot', 'empty'])
def test_synthetic_negative_pages_cannot_be_positive_records(label):
    pages = {'login': b'<html><form>Login required</form></html>',
             'captcha': b'<html>Complete CAPTCHA</html>',
             'bot': b'<html>Access denied</html>', 'empty': b''}
    with pytest.raises(SourceError):
        parse_b2b_center_listing(pages[label])
    with pytest.raises(SourceError):
        parse_eis_223_feed(pages[label])


def test_synthetic_external_detail_in_real_capture_is_rejected():
    payload = (FIXTURES / 'b2b_search.html').read_bytes().replace(
        b'https://www.b2b-center.ru/search/number/', b'https://evil.invalid/search/number/', 1)
    with pytest.raises(SourceError):
        parse_b2b_center_listing(payload)


def test_local_wrapper_request_budget_and_timeout_contract():
    class Probe:
        async def fetch(self, limit):
            policy = _policy.get()
            assert policy.hosts == HOSTS['b2b_center']
            assert policy.max_requests == 1 and policy.max_bytes == 5 * 1024 * 1024
            assert limit == 20
            return []
    assert asyncio.run(LocalBoundedSource(Probe(), 'b2b_center').fetch(100)) == []
    assert _policy.get() is None


def test_exact_hosts_reject_external_and_credentials():
    import httpx
    policy = FetchPolicy(HOSTS['b2b_center'], 1)
    for url in ('https://evil.invalid/', 'https://www.b2b-center.ru.evil.invalid/',
                'http://www.b2b-center.ru/', 'https://user:password@www.b2b-center.ru/',
                'https://www.b2b-center.ru:444/'):
        with pytest.raises(ConnectorTransportError):
            _validate_bounded_url(httpx.URL(url), policy)


def test_synthetic_duplicate_counterpart_links_without_new_unique_claim():
    from app.sources.models import TenderNotice
    records = captured_records()
    # Explicit synthetic comparator, never a real EIS retrieval fixture.
    counterpart = TenderNotice(source='eis', external_id='synthetic-counterpart', title='Synthetic',
        tender_number='0338200012226000019',
        url='https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=0338200012226000019')
    links = duplicate_diagnostics([*records, counterpart])['cross_source_links']
    assert links['0338200012226000019'] == [
        ['b2b_center', 'l0338200012226000019-1'], ['eis', 'synthetic-counterpart']]


def test_existing_ingestion_routing_requires_local_opt_ins():
    from app.sources.ingestion import validate_payload, connector_version
    from app.jobs.worker import PermanentJobError
    for key in ('eis', 'eis_223', 'b2b_center'):
        payload = {'schema': 1, 'source_id': key, 'sync_window': '2026-10-13T20Z',
                   'connector_version': connector_version(key)}
        configured = local_catalog(enable_eis223=True, enable_b2b=True)
        assert validate_payload(payload, configured.registry).key == key
        if key != 'eis':
            with pytest.raises(PermanentJobError):
                validate_payload(payload, local_catalog().registry)


def test_host_smoke_json_failure_states_without_network(tmp_path, monkeypatch):
    import importlib.util
    import app.sources.ru08_integration as integration
    spec = importlib.util.spec_from_file_location('ru08_smoke', Path(__file__).with_name('ru08_six_live_smoke.py'))
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)

    class Denied:
        async def fetch(self, limit=20):
            raise SourceError('Synthetic denial; no outbound request')

    catalog = local_catalog(enable_eis223=True, enable_b2b=True)
    registry = SourceRegistry(replace(item, source=type('DeniedSource', (Denied,), {'name': item.key})())
                              if item.enabled else item for item in catalog.registry.registrations())
    blocked = SourceCatalog(registry, MultiSourceFetcher(registry, concurrency=1))
    monkeypatch.setattr(integration, 'local_catalog', lambda **kwargs: blocked)
    result = asyncio.run(smoke.run(tmp_path))
    assert set(result) == {'sources', 'ai_query_verified', 'note'}
    assert set(result['sources']) == set(SOURCE_KEYS)
    assert result['ai_query_verified'] is False
    for key, entry in result['sources'].items():
        assert set(entry) == {'state', 'real_records', 'database_upserts', 'query_matches', 'reason'}
        assert entry['state'] == ('OFFLINE_ONLY' if key == 'tektorg' else 'BLOCKED')
        assert entry['real_records'] == entry['database_upserts'] == entry['query_matches'] == 0
