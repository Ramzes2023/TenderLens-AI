"""Shipped dashboard + authenticated synthetic API, entirely offline HTTP mocks."""
from pathlib import Path
import json
import sys
from urllib.parse import urlsplit
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Reuse readable installed PDF packages without inheriting PYTHONPATH/.env.
sys.path.append(str(ROOT / '.ui-fix-venv/Lib/site-packages'))
import dotenv
dotenv.load_dotenv = lambda *args, **kwargs: False

import httpx
from playwright.sync_api import sync_playwright
from tests.test_organization_workflows import OrganizationWorkflowTests
from tests.test_international_sources import fixture
from scripts.international_sources_live_probe import international_catalog
from app.sources.http import source_client
from app.database.repository import TenderRepository

OUT = ROOT / 'artifacts/intl-sources-20261014_162147'


def main():
    helper = OrganizationWorkflowTests()
    helper.setUp()
    try:
        helper.as_account(helper.owner)
        profile = dict(helper.profile('Synthetic international company', 'aluminium'),
                       accepted_currencies=['EUR', 'GBP'], allowed_countries=['IT', 'GB'])
        created = helper.client.post(helper.base('/companies'), json={'name': profile['company_name'], 'profile': profile})
        assert created.status_code == 201
        runtime = helper.client.app.state.runtime
        runtime.source_catalog = international_catalog()
        repository = TenderRepository(helper.path)
        repository.initialize()
        runtime.tender_repository = repository
        from datetime import datetime, timezone
        payloads = {key: fixture(key) for key in ('ted', 'uk_fts', 'world_bank')}
        payloads['ted']['notices'][0]['deadline-receipt-tender-date-lot'] = '2099-11-01'
        payloads['uk_fts']['releases'][0]['tender']['tenderPeriod']['endDate'] = '2099-11-01T12:00:00Z'
        payloads['world_bank']['data'][0]['deadline_date'] = '01-Nov-2099'
        payloads['world_bank']['data'][0]['publication_date'] = datetime.now(timezone.utc).strftime('%d-%b-%Y')
        def respond(request):
            source = {'api.ted.europa.eu': 'ted', 'www.find-tender.service.gov.uk': 'uk_fts',
                      'datacatalogapi.worldbank.org': 'world_bank'}[request.url.host]
            return httpx.Response(200, json=payloads[source])
        def client(**kwargs):
            return source_client(**kwargs, transport=httpx.MockTransport(respond))
        with patch('app.sources.ted_api.source_client', client), patch('app.sources.uk_fts_api.source_client', client), patch('app.sources.world_bank.source_client', client), sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path='C:/Users/ramze/AppData/Local/VALYQON/v7-browser-tools/browsers/chromium-1243/chrome-win64/chrome.exe')
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors, responses = [], []
                page.on('pageerror', lambda error: errors.append(str(error)))
                def route_handler(route):
                    request = route.request
                    parts = urlsplit(request.url)
                    if parts.hostname != 'testserver':
                        route.abort()
                        return
                    path = parts.path + ('?' + parts.query if parts.query else '')
                    response = helper.client.request(request.method, path, content=request.post_data_buffer,
                        headers={k: v for k, v in request.headers.items() if k not in ('host', 'cookie', 'content-length')}, follow_redirects=False)
                    responses.append({'path': parts.path, 'status': response.status_code})
                    route.fulfill(status=response.status_code, body=response.content,
                        headers={k: v for k, v in response.headers.items() if k not in ('content-length', 'content-encoding', 'transfer-encoding')})
                page.route('**/*', route_handler)
                page.goto('http://testserver/dashboard#discover')
                page.wait_for_selector('#organizationSelect')
                page.select_option('#organizationSelect', str(helper.organization.id))
                page.wait_for_function('usingSharedOrganization() && Number.isInteger(state.activeCompanyId)')
                page.wait_for_function('!document.querySelector("#discoverButton").disabled')
                with page.expect_response('**/discover/tenders') as discovery:
                    page.click('#discoverButton')
                assert discovery.value.status == 200
                data = discovery.value.json()
                assert len(data['items']) == 3
                page.wait_for_selector('#discoveryResults .tender-card')
                assert page.locator('#discoveryResults .tender-card').count() == 3
                assert page.locator('#discoveryResults a[href^="https://projects.worldbank.org/"]').count() == 1
                assert 'World Bank' in page.locator('#discoverySourceOutcomes').inner_text()
                page.screenshot(path=str(OUT / 'international_discovery_en.png'), full_page=True)
                page.locator('#discoveryResults').screenshot(path=str(OUT / 'international_results.png'))
                page.select_option('#shellLocale', 'ru')
                assert 'Всемирного банка' in page.locator('#discoverySourceOutcomes').inner_text()
                page.screenshot(path=str(OUT / 'international_discovery_ru.png'), full_page=True)
                page.evaluate("location.hash='source-health'")
                page.wait_for_selector('#sourceHealthResults .tender-card')
                assert page.locator('#sourceHealthResults .tender-card').count() == 3
                page.screenshot(path=str(OUT / 'international_source_health.png'))
                assert not errors, errors
                result = {'status': 'PASS', 'mode': 'authenticated synthetic temporary SQLite, official HTTP mocked',
                          'visible_sources': ['ted', 'uk_fts', 'world_bank'], 'errors': errors,
                          'responses': responses, 'live_network': False}
                (OUT / 'browser_results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
                print(json.dumps(result, indent=2))
            finally:
                browser.close()
    finally:
        helper.doCleanups()


if __name__ == '__main__':
    main()
