"""Actual adapters through authenticated synthetic shared-company discovery."""
import json
from unittest.mock import patch

import httpx
import pytest

from app.sources.catalog import SourceCatalog
from app.sources.multi import MultiSourceFetcher
from app.sources.registry import SourceRegistration, SourceRegistry
from app.sources.ted_api import TedApiSource
from app.sources.uk_fts_api import UkFindTenderApiSource
from app.sources.world_bank import WorldBankSource
from app.sources.http import source_client
from tests.test_international_sources import fixture

with patch('dotenv.load_dotenv', return_value=False):
    import tests.test_organization_workflows as workflows
    from app.database.repository import TenderRepository


@pytest.mark.parametrize('world_bank_failed', [False, True])
def test_scoped_discovery_health_history_saving(world_bank_failed):
    calls = []
    payloads = {name: fixture(name) for name in ('ted', 'uk_fts', 'world_bank')}
    # Network tests use durable synthetic deadlines; parser date precision is
    # independently tested against an injected clock in the parser suite.
    payloads['ted']['notices'][0]['deadline-receipt-tender-date-lot'] = '2099-11-01'
    payloads['uk_fts']['releases'][0]['tender']['tenderPeriod']['endDate'] = '2099-11-01T12:00:00+01:00'
    payloads['world_bank']['data'][0]['deadline_date'] = '01-Nov-2099'
    from datetime import datetime, timezone
    payloads['world_bank']['data'][0]['publication_date'] = datetime.now(timezone.utc).strftime('%d-%b-%Y')

    def respond(request):
        calls.append(request)
        assert request.url.scheme == 'https' and 'authorization' not in request.headers
        key = {'api.ted.europa.eu': 'ted', 'www.find-tender.service.gov.uk': 'uk_fts',
               'datacatalogapi.worldbank.org': 'world_bank'}[request.url.host]
        if key == 'world_bank' and world_bank_failed:
            return httpx.Response(403, json={})
        return httpx.Response(200, json=payloads[key])

    def client(**kwargs):
        return source_client(**kwargs, transport=httpx.MockTransport(respond))

    registry = SourceRegistry(SourceRegistration(key=source.name, display_name=label, source=source)
        for source, label in [(TedApiSource(), 'TED'), (UkFindTenderApiSource(), 'UK Find a Tender'),
                              (WorldBankSource(), 'World Bank Finances One')])
    catalog = SourceCatalog(registry, MultiSourceFetcher(registry))
    helper = workflows.OrganizationWorkflowTests()
    with patch('dotenv.load_dotenv', return_value=False):
        helper.setUp()
    try:
        helper.as_account(helper.owner)
        profile = dict(helper.profile('Synthetic international aluminium company', 'aluminium'),
                       accepted_currencies=['EUR', 'GBP'], allowed_countries=['IT', 'GB'])
        created = helper.client.post(helper.base('/companies'), json={'name': profile['company_name'], 'profile': profile})
        assert created.status_code == 201, created.text
        runtime = helper.client.app.state.runtime
        runtime.source_catalog = catalog
        repository = TenderRepository(helper.path)
        repository.initialize()
        runtime.tender_repository = repository
        with patch('app.sources.ted_api.source_client', client), patch('app.sources.uk_fts_api.source_client', client), patch('app.sources.world_bank.source_client', client):
            result = helper.client.post(helper.base('/discover/tenders'))
            assert result.status_code == 200, result.text
            data = result.json()
            assert data['attempted_sources'] == ['ted', 'uk_fts', 'world_bank']
            assert data['partial_failure'] is world_bank_failed
            assert len(data['items']) == (2 if world_bank_failed else 3)
            assert data['history_id']
            for health in data['source_statuses']:
                assert health['coverage']
                if health['source'] == 'world_bank' and world_bank_failed:
                    assert health['state'] == 'failed' and 'HTTP 403' in health['diagnostic']
                else:
                    assert health['state'] == 'healthy' and health['last_successful_sync']
            history = helper.client.get(helper.base('/discovery/history'))
            assert history.status_code == 200 and history.json()[0]['result_count'] == len(data['items'])
            saved = helper.client.post(helper.base('/shortlist'), json=data['items'][0])
            assert saved.status_code == 200, saved.text
            before = len(calls)
            helper.as_account(helper.outsider)
            assert helper.client.post(helper.base('/discover/tenders')).status_code == 403
            assert helper.client.get(helper.base('/discovery/history')).status_code == 403
            assert len(calls) == before
            helper.as_account(helper.owner)
            narrow = dict(profile, product_keywords=['aluminium constructions'], search_keywords=['aluminium constructions'])
            assert helper.client.patch(helper.base(f"/companies/{created.json()['id']}"), json={'profile': narrow}).status_code == 200
            result = helper.client.post(helper.base('/discover/tenders'))
            assert result.status_code == 200
            assert result.json()['items'] == [] and len(result.json()['attempted_sources']) == 3
    finally:
        helper.doCleanups()
