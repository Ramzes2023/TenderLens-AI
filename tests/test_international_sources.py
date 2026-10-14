"""Deterministic international normalization and transport contracts."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json

import httpx
import pytest

from app.sources.http import source_client
from app.sources.international import source_date, official_url, request_json
from app.sources.ted_api import TedApiSource, parse_ted_search_response
from app.sources.uk_fts_api import UkFindTenderApiSource, parse_uk_fts_response
from app.sources.world_bank import WorldBankSource, WorldBankSourceError, parse_world_bank_response
from app.sources.opportunities import validate_notice

FIXTURES = Path(__file__).parent / 'fixtures/international'
NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


def fixture(name):
    return json.loads((FIXTURES / f'{name}.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('name,parser', [('ted', parse_ted_search_response), ('uk_fts', parse_uk_fts_response), ('world_bank', parse_world_bank_response)])
def test_mapping_and_identity(name, parser):
    notices = parser(fixture(name), now=NOW)
    assert len(notices) == 1
    notice = notices[0]
    validate_notice(notice, name)
    assert 'construction' in notice.title.lower()
    assert notice.enrichment['country']['status'] != 'missing'
    assert notice.enrichment['public_metadata']['attribution']
    assert notice.enrichment['observed_at']
    assert notice.identity == (name, notice.external_id)
    if name == 'world_bank':
        assert notice.currency is None and notice.initial_price is None and notice.customer is None
        assert notice.deadline == '2026-11-01'
    elif name == 'uk_fts':
        assert notice.deadline == '2026-11-01T11:00:00+00:00'
        assert notice.external_id == 'ocds-h6vhtk-synthetic'
    else:
        assert notice.published_at == '2026-10-14'


@pytest.mark.parametrize('name,parser,key', [('ted', parse_ted_search_response, 'notices'), ('uk_fts', parse_uk_fts_response, 'releases'), ('world_bank', parse_world_bank_response, 'data')])
def test_empty_malformed_and_duplicate(name, parser, key):
    assert parser({key: []}, now=NOW) == []
    with pytest.raises(Exception):
        parser({key: 'invalid'}, now=NOW)
    payload = fixture(name)
    payload[key].append(deepcopy(payload[key][0]))
    assert len(parser(payload, now=NOW)) == 1


def test_world_bank_closed_sparse_award_and_bad_urls():
    raw = fixture('world_bank')['data'][0]
    for changes in ({'deadline_date': '01-Jan-2005'}, {'deadline_date': None},
                    {'notice_type': 'Contract Award'}, {'bid_description': ''}):
        assert parse_world_bank_response({'data': [{**raw, **changes}]}, now=NOW) == []
    for url in ('https://projects.worldbank.org.evil.test/a', 'http://projects.worldbank.org/a',
                'https://user@projects.worldbank.org/a', 'https://projects.worldbank.org/not-a-notice'):
        with pytest.raises(WorldBankSourceError):
            parse_world_bank_response({'data': [{**raw, 'url': url}]}, now=NOW)


def test_uk_cancellation_supersedes_tender_and_awards_are_excluded():
    payload = fixture('uk_fts')
    cancelled = deepcopy(payload['releases'][0])
    cancelled.update(date='2026-10-14T13:00:00Z', tag=['tenderCancellation'])
    cancelled['tender']['status'] = 'cancelled'
    payload['releases'].append(cancelled)
    assert parse_uk_fts_response(payload, now=NOW) == []


def test_ted_expired_award_timeout_and_query_escaping():
    payload = fixture('ted')
    payload['notices'][0]['deadline-receipt-tender-date-lot'] = '2005-01-01'
    assert parse_ted_search_response(payload, now=NOW) == []
    payload['notices'][0]['notice-type'] = 'can-standard'
    assert parse_ted_search_response(payload, now=NOW) == []
    query = TedApiSource().for_search_terms(['aluminium profiles" OR OJ = ()']).query
    assert '"aluminium profiles OR OJ"' in query and '()' not in query


@pytest.mark.parametrize('value,expected', [('2026-10-14+02:00', '2026-10-14'), ('14-Oct-2026', '2026-10-14'),
    ('2026-10-14T12:00:00+02:00', '2026-10-14T10:00:00+00:00')])
def test_dates(value, expected):
    assert source_date(value) == expected


def test_dates_do_not_invent_timezone():
    for value in ('2026-10-14T12:00:00', '2026-10-14T12:00:00-00:00', '2026-10-14+99:99'):
        with pytest.raises(ValueError):
            source_date(value)


@pytest.mark.parametrize('status', [401, 403, 429, 500])
def test_http_failures_and_retry_after(status):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, headers={'Retry-After': '11'}, json={})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await request_json(client, 'GET', 'https://datacatalogapi.worldbank.org/a', hosts={'datacatalogapi.worldbank.org'})
    asyncio.run(run())
    assert len(calls) == 1  # Don't violate an 11-second server backoff.


def test_retry_once_and_malformed_json():
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) == 1 else 200, headers={'Retry-After': '0'}, json={'data': []})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await request_json(client, 'GET', 'https://datacatalogapi.worldbank.org/a', hosts={'datacatalogapi.worldbank.org'})
    assert asyncio.run(run()) == {'data': []}
    assert len(calls) == 2


def test_world_bank_bounded_pagination_and_recent_filter(monkeypatch):
    calls = []
    record = fixture('world_bank')['data'][0]
    def respond(request):
        calls.append(request)
        assert request.url.params['filter'].startswith('publication_date>=')
        return httpx.Response(200, json={'data': [dict(record, id=1000+i) for i in range(100)]})
    monkeypatch.setattr('app.sources.world_bank.source_client', lambda **kw: source_client(**kw, transport=httpx.MockTransport(respond)))
    asyncio.run(WorldBankSource().fetch(5))
    assert len(calls) == 2
    assert [r.url.params['skip'] for r in calls] == ['0', '100']


def test_uk_cursor_pagination_cancellation_and_ssrf(monkeypatch):
    calls = []
    def respond(request):
        calls.append(request)
        payload = fixture('uk_fts')
        if len(calls) == 1:
            payload['links'] = {'next': 'https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?cursor=abc'}
        return httpx.Response(200, json=payload)
    monkeypatch.setattr('app.sources.uk_fts_api.source_client', lambda **kw: source_client(**kw, transport=httpx.MockTransport(respond)))
    assert len(asyncio.run(UkFindTenderApiSource().fetch(5))) == 1
    assert len(calls) == 2 and calls[1].url.params['cursor'] == 'abc'
    with pytest.raises(ValueError):
        official_url('https://127.0.0.1/a', {'www.find-tender.service.gov.uk'})


@pytest.mark.parametrize('adapter,module', [(TedApiSource(), 'ted_api'), (UkFindTenderApiSource(), 'uk_fts_api'), (WorldBankSource(), 'world_bank')])
def test_source_timeout_diagnostics(monkeypatch, adapter, module):
    def respond(request):
        raise httpx.ReadTimeout('synthetic timeout')
    monkeypatch.setattr(f'app.sources.{module}.source_client', lambda **kw: source_client(**kw, transport=httpx.MockTransport(respond)))
    with pytest.raises(Exception, match='timeout:'):
        asyncio.run(adapter.fetch(5))


@pytest.mark.parametrize('adapter,module', [(TedApiSource(), 'ted_api'), (UkFindTenderApiSource(), 'uk_fts_api'), (WorldBankSource(), 'world_bank')])
def test_registry_worker_ingestion_and_safe_retry(monkeypatch, adapter, module):
    from types import SimpleNamespace
    from app.sources.catalog import SourceCatalog
    from app.sources.registry import SourceRegistry, SourceRegistration
    from app.sources.multi import MultiSourceFetcher
    from app.sources.ingestion import ConnectorSyncHandler, SYSTEM_SCOPE, connector_version, sync_window
    from app.jobs.worker import RetryableJobError
    registry = SourceRegistry([SourceRegistration(key=adapter.name, display_name=adapter.name, source=adapter)])
    catalog = SourceCatalog(registry, MultiSourceFetcher(registry))
    stored = []
    store = SimpleNamespace(upsert=lambda notice, version: stored.append((notice, version)) or True)
    handler = ConnectorSyncHandler(catalog, store, max_records=5)
    context = SimpleNamespace(job=SimpleNamespace(scope=SYSTEM_SCOPE), should_stop=False)
    payload = {'schema': 1, 'source_id': adapter.name, 'sync_window': sync_window(), 'connector_version': connector_version(adapter.name)}
    data = fixture(adapter.name)
    if adapter.name == 'world_bank':
        data['data'][0]['publication_date'] = datetime.now(timezone.utc).strftime('%d-%b-%Y')
    def respond(request):
        return httpx.Response(200, json=data)
    monkeypatch.setattr(f'app.sources.{module}.source_client', lambda **kw: source_client(**kw, transport=httpx.MockTransport(respond)))
    result = handler(context, payload)
    assert result['accepted_count'] == 1 and len(stored) == 1
    validate_notice(stored[0][0], adapter.name)
    def unavailable(request):
        return httpx.Response(429, headers={'Retry-After': '11'}, json={})
    monkeypatch.setattr(f'app.sources.{module}.source_client', lambda **kw: source_client(**kw, transport=httpx.MockTransport(unavailable)))
    with pytest.raises(RetryableJobError):
        handler(context, payload)
