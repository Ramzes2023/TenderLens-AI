"""Real public adapters -> catalog -> scoped Discovery; no external traffic."""
import asyncio
from copy import deepcopy
from unittest.mock import patch

import httpx
import pytest

from app.sources.http import source_client, FetchPolicy, bounded_fetch
from app.sources.uk_fts_api import parse_uk_fts_response
from app.sources.eis_rss import SourceError
from scripts.phase24_public_sources_live_probe import public_catalog, probe

# Same safety wrapper used by the existing PDF integration fixture.
with patch('dotenv.load_dotenv', return_value=False), patch('app.api.config.load_dotenv', return_value=False):
    import tests.test_organization_workflows as workflows


def ted_record(number, title):
    return {'publication-number': number, 'notice-title': {'eng': title, 'fra': 'Pompes'},
            'buyer-name': {'eng': 'Synthetic public buyer'}, 'publication-date': '2026-10-01',
            'deadline-receipt-tender-date-lot': '2099-01-01', 'total-value': 10000,
            'total-value-cur': 'EUR', 'description-proc': title}


def uk_record(ocid, number, status='active', date='2026-10-01T12:00:00Z'):
    return {'ocid': ocid, 'id': number, 'date': date, 'tag': ['tender'],
            'buyer': {'name': 'Synthetic UK buyer'}, 'tender': {
                'id': number, 'status': status, 'title': 'Supply of industrial pumps',
                'description': '<p>industrial pumps</p>',
                'value': {'amount': 9000, 'currency': 'GBP'},
                'tenderPeriod': {'endDate': '2099-01-01T12:00:00+00:00'}}}


def fixtures():
    fit = ted_record('100001-2026', 'Supply of industrial pumps')
    return {'notices': [fit, deepcopy(fit), ted_record('100002-2026', 'Used industrial pumps'),
                        ted_record('100003-2026', 'Office furniture')]}, {'releases': [
        uk_record('ocds-test-active', '100004-2026'),
        uk_record('ocds-test-cancel', '100005-2026'),
        uk_record('ocds-test-cancel', '100006-2026', 'cancelled', '2026-10-02T12:00:00Z'),
        dict(uk_record('ocds-test-award', '100007-2026'), tag=['award'])]}


@pytest.mark.parametrize('uk_failed', [False, True])
def test_actual_adapters_catalog_scoped_http_and_preliminary_fit(uk_failed):
    ted, uk = fixtures()
    calls = []

    def respond(request):
        calls.append(request)
        assert request.url.scheme == 'https'
        assert 'authorization' not in request.headers
        if request.url.host == 'api.ted.europa.eu':
            assert request.method == 'POST'
            return httpx.Response(200, json=ted)
        assert request.url.host == 'www.find-tender.service.gov.uk'
        assert request.method == 'GET'
        return httpx.Response(503 if uk_failed else 200, json=uk)

    def client(**kwargs):
        return source_client(**kwargs, transport=httpx.MockTransport(respond))

    w = workflows.OrganizationWorkflowTests()
    w.setUp()
    try:
        w.as_account(w.owner)
        profile = dict(w.profile('Pump supplier', 'industrial pumps'), accepted_currencies=['EUR', 'GBP'],
                       excluded_keywords=['used'])
        company = w.client.post(w.base('/companies'), json={'name': 'Pump supplier', 'profile': profile})
        assert company.status_code == 201, company.text
        second = w.create_company('Furniture supplier', 'furniture')
        w.client.app.state.runtime.source_catalog = public_catalog()
        with patch('app.sources.ted_api.source_client', client), patch('app.sources.uk_fts_api.source_client', client), bounded_fetch(
                FetchPolicy(frozenset({'api.ted.europa.eu', 'www.find-tender.service.gov.uk'}), 8, max_bytes=2097152)):
            for account in (w.owner, w.member, w.viewer):
                w.as_account(account)
                response = w.client.post(w.base('/discover/tenders'))
                assert response.status_code == 200, response.text
                result = response.json()
                assert result['attempted_sources'] == ['ted', 'uk_fts']
                assert result['partial_failure'] is uk_failed
                assert result['failed_sources'] == (['uk_fts'] if uk_failed else [])
                assert len(result['source_statuses']) == 2
                items = result['items']
                assert len(items) == (1 if uk_failed else 2)
                assert len({(i['source'], i['external_id']) for i in items}) == len(items)
                for item in items:
                    assert item['analysis_stage'] == 'metadata_preview'
                    assert item['full_ai_analyzed'] is False
                    assert item['preliminary_scoring']['profile_name'] == 'Pump supplier'
                    assert item['currency'] in ('EUR', 'GBP')
                    assert item['region'] is None  # Buyer jurisdiction is not delivery country.
                    assert item['url'].startswith(('https://ted.europa.eu/', 'https://www.find-tender.service.gov.uk/'))
            before = len(calls)
            w.as_account(w.outsider)
            assert w.client.post(w.base('/discover/tenders')).status_code == 403
            assert len(calls) == before
            w.as_account(w.owner)
            assert w.client.post(w.base(f"/companies/{second['id']}/activate")).status_code == 200
            response = w.client.post(w.base('/discover/tenders'))
            assert response.status_code == 200, response.text
            assert [i['external_id'] for i in response.json()['items']] == ['100003-2026']
    finally:
        w.doCleanups()


def test_uk_closed_invalid_dates_and_nonfinite_value():
    record = uk_record('ocds-test', '100008-2026')
    record['tender']['tenderPeriod']['endDate'] = '2000-01-01T00:00:00Z'
    assert parse_uk_fts_response({'releases': [record]}) == []
    record['tender']['tenderPeriod']['endDate'] = '2099-01-01T00:00:00'  # Unknown offset.
    with pytest.raises(SourceError):
        parse_uk_fts_response({'releases': [record]})
    record['tender']['tenderPeriod'] = {}
    record['tender']['value']['amount'] = 'NaN'
    parsed = parse_uk_fts_response({'releases': [record]})[0]
    assert parsed.initial_price is None and parsed.deadline is None
    assert parsed.currency == 'GBP'


def test_probe_default_never_constructs_network_client():
    with patch('scripts.phase24_public_sources_live_probe.public_catalog', side_effect=AssertionError('network')):
        report, code = asyncio.run(probe())
    assert code != 0 and report['outbound_calls'] == 0 and report['attempted_source_keys'] == []


@pytest.mark.parametrize('empty', [False, True])
def test_live_probe_contract_with_actual_adapters_and_bounded_mock_transport(empty):
    ted, uk = fixtures()

    def respond(request):
        if request.url.host == 'api.ted.europa.eu':
            return httpx.Response(200, json={'notices': []} if empty else ted)
        return httpx.Response(200, json={'releases': []} if empty else uk)

    def client(**kwargs):
        return source_client(**kwargs, transport=httpx.MockTransport(respond))

    with patch('app.sources.ted_api.source_client', client), patch('app.sources.uk_fts_api.source_client', client):
        report, code = asyncio.run(probe(live=True))
    assert report['outbound_calls'] == 2
    assert code == (1 if empty else 0)
    assert report['sam_gov']['status'] == 'AUTH_REQUIRED'
    for key, source in report['sources'].items():
        assert source['status'] == ('UNAVAILABLE' if empty else 'LIVE_VERIFIED')
        assert source['transport']['http_status'] is None
        assert len(source['examples']) <= 3
        assert 'score' not in str(source['examples'])
