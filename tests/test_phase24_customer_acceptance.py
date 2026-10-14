"""LOCAL SYNTHETIC TEST: real sessions/RBAC/scoped handlers; no PostgreSQL or LLM.

Only source HTTP and Saved persistence are injected. Auth/company/monitoring use
the existing disposable SQLite fixture. Synthetic TED-schema records are not live evidence.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

with patch('dotenv.load_dotenv', return_value=False), patch('app.api.config.load_dotenv', return_value=False):
    from tests import test_organization_workflows as workflows

from app.api.schemas import TenderDiscoveryResponse
from app.database import DatabaseAuthorizationError
from app.sources.http import source_client
from app.tenancy import organization_owner_id
from scripts.phase24_customer_acceptance_probe import fixture_payload, probe, ted_catalog


class ScopedMemorySaved:
    """Storage double retains real organization-service role and company checks."""
    def __init__(self, harness):
        self.harness = harness
        self.rows = []

    def authorize(self, account_id, organization_id, company_id, write=False):
        account = next(a for a in (self.harness.owner, self.harness.member,
                                   self.harness.viewer, self.harness.outsider) if a.id == account_id)
        try:
            self.harness.organizations.require_membership(
                account, organization_id, {'owner', 'admin', 'member'} if write else None)
            if self.harness.companies.get_for_organization(account_id, organization_id, company_id) is None:
                raise ValueError('Missing scoped company')
        except Exception:
            raise DatabaseAuthorizationError('Synthetic storage scope denied') from None

    def save_opportunity_for_organization(self, **kwargs):
        self.authorize(kwargs['account_id'], kwargs['organization_id'], kwargs['company_id'], True)
        key = (kwargs['organization_id'], kwargs['company_id'], kwargs['source'], kwargs['external_id'])
        for row in self.rows:
            if (row.organization_id, row.company_id, row.source, row.external_id) == key:
                return row
        row = SimpleNamespace(**kwargs, id=len(self.rows) + 1,
                              created_at='2026-10-13T00:00:00Z', updated_at='2026-10-13T00:00:00Z')
        self.rows.append(row)
        return row

    def list_saved_opportunities_for_organization(self, account_id, organization_id, company_id, limit):
        self.authorize(account_id, organization_id, company_id)
        return [r for r in self.rows if (r.organization_id, r.company_id) == (organization_id, company_id)][:limit]


@pytest.fixture
def customer():
    harness = workflows.OrganizationWorkflowTests()
    harness.setUp()
    harness.as_account(harness.owner)
    try:
        yield harness
    finally:
        harness.doCleanups()


def install_ted(monkeypatch, customer, payload=None, status=200, after_fetch=None):
    calls = []
    def respond(request):
        calls.append(request)
        assert str(request.url) == 'https://api.ted.europa.eu/v3/notices/search'
        assert request.method == 'POST' and 'authorization' not in request.headers
        if after_fetch:
            after_fetch()
        return httpx.Response(status, json=fixture_payload() if payload is None else payload)
    monkeypatch.setattr('app.sources.ted_api.source_client',
                        lambda **kwargs: source_client(**kwargs, transport=httpx.MockTransport(respond)))
    customer.client.app.state.runtime.source_catalog = ted_catalog()
    return calls


def cable_company(customer):
    profile = dict(customer.profile('SYNTHETIC cable supplier', 'cables'),
                   accepted_currencies=['EUR'], max_contract_value=1000000,
                   hard_stop_on_currency=True)
    response = customer.client.post(customer.base('/companies'),
                                    json={'name': profile['company_name'], 'profile': profile})
    assert response.status_code == 201, response.text
    return response.json()


def criteria(score):
    return {row['code']: row for row in score['criteria']}


def test_authorized_discover_explainable_score_saved_monitoring_and_isolation(customer, monkeypatch):
    w = customer
    company = cable_company(w)
    calls = install_ted(monkeypatch, w)
    url = w.base('/discover/tenders')
    response = w.client.post(url, headers={'Origin': 'http://testserver', 'Sec-Fetch-Site': 'same-origin'})
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    report = TenderDiscoveryResponse.model_validate(response.json()).model_dump(mode='json')
    assert report['attempted_sources'] == report['successful_sources'] == ['ted']
    assert not report['total_failure'] and not report['partial_failure']
    items = {i['external_id']: i for i in report['items']}
    assert set(items) == {'100001-2026', '100002-2026'}  # Furniture excluded by actual prefilter.
    for item in items.values():
        assert item['url'] == f"https://ted.europa.eu/en/notice/{item['external_id']}/html"
        assert item['reasons']
        assert item['analysis_stage'] == 'metadata_preview' and not item['full_ai_analyzed']
        assert item['full_analysis'] is None and item['full_scoring'] is None
        assert item['preliminary_provenance']['company_id'] == company['id']
        assert criteria(item['preliminary_scoring'])['category']['status'] == 'matched'
        assert criteria(item['preliminary_scoring'])['documents']['status'] == 'not_scored'
    unknown = items['100002-2026']
    assert unknown['deadline'] is None and unknown['initial_price'] is None
    assert criteria(unknown['preliminary_scoring'])['budget']['status'] == 'not_scored'
    assert criteria(unknown['preliminary_scoring'])['budget']['explanation']
    assert len(w.client.post(url).json()['items']) == 2
    assert not w.monitoring_repository.seen(organization_owner_id(w.organization.id),
                                          f"ted:company:{company['id']}", '100001-2026')
    # Real scoped evaluation consumes supplied document facts; it does not run AI or attest a PDF.
    document = dict(title='Supply of cables', procurement_object='cables',
                    initial_price=10000, currency='USD', required_documents=['ISO certificate'],
                    missing_information=['Delivery location missing from synthetic document'])
    score = w.client.post(w.base('/scoring/evaluate'), json=document)
    assert score.status_code == 200, score.text
    assert criteria(score.json())['budget']['status'] == 'failed'
    assert score.json()['stop_factors']
    negative = w.client.post(w.base('/scoring/evaluate'), json=dict(document, title='Furniture', procurement_object='chairs'))
    assert criteria(negative.json())['category']['status'] == 'failed'

    saved = ScopedMemorySaved(w)
    # Discover history is intentionally optional; attach Saved storage after discovery.
    w.client.app.state.runtime.tender_repository = saved
    item = items['100001-2026']
    result = w.client.post(w.base('/shortlist'), json=item)
    assert result.status_code == 200, result.text
    assert result.json()['company_id'] == company['id']
    assert w.client.post(w.base('/shortlist'), json=item).json()['id'] == result.json()['id']
    assert len(w.client.get(w.base('/shortlist')).json()) == 1
    w.as_account(w.viewer)
    assert w.client.post(w.base('/shortlist'), json=item).status_code == 403
    assert w.client.post(w.base('/monitoring/scan')).status_code == 403
    w.as_account(w.owner)
    # Existing monitoring service receives the same parsed TED notices, no network.
    from app.sources.ted_api import parse_ted_search_response
    w.monitoring.source = workflows.DynamicSource(parse_ted_search_response(fixture_payload()))
    first = w.client.post(w.base('/monitoring/scan'))
    assert first.status_code == 200, first.text
    assert {i['external_id'] for i in first.json()} == set(items)
    assert w.client.post(w.base('/monitoring/scan')).json() == []
    other = w.create_company('SYNTHETIC furniture supplier', 'furniture')
    assert w.client.post(w.base(f"/companies/{other['id']}/activate")).status_code == 200
    assert w.client.get(w.base('/shortlist')).json() == []
    assert w.client.post(w.base('/shortlist'), json=item).status_code == 409
    isolated = w.client.post('/api/v1/organizations', json={'name': 'SYNTHETIC isolated tenant'}).json()['id']
    base = f'/api/v1/organizations/{isolated}'
    assert w.client.get(base + f"/companies/{company['id']}").status_code == 404
    assert w.client.post(base + '/discover/tenders').status_code == 409  # No personal fallback.
    before = len(calls)
    w.as_account(w.outsider)
    assert w.client.post(url).status_code == 403
    assert w.client.post(w.base('/shortlist'), json=item).status_code == 403
    assert len(calls) == before
    w.client.cookies.clear()
    assert w.client.post(url).status_code == 401


@pytest.mark.parametrize('path', ['/discover/tenders', '/scoring/evaluate', '/shortlist', '/monitoring/scan'])
def test_cross_site_write_rejected(customer, path):
    cable_company(customer)
    response = customer.client.post(customer.base(path),
        json={} if path != '/scoring/evaluate' else {'title': 'Synthetic'},
        headers={'Origin': 'https://evil.example', 'Sec-Fetch-Site': 'cross-site'})
    # Shortlist body must be valid to reach the route's origin guard.
    if path == '/shortlist':
        from app.api.organization_workflow_routes import _discovery_item
        from app.monitoring.service import prefilter_notice
        from app.sources.ted_api import parse_ted_search_response
        from scripts.phase24_customer_acceptance_probe import synthetic_profile
        profile = synthetic_profile()
        item = _discovery_item(prefilter_notice(parse_ted_search_response(fixture_payload())[0], profile), profile)
        response = customer.client.post(customer.base(path), json=item.model_dump(mode='json'),
            headers={'Origin': 'https://evil.example', 'Sec-Fetch-Site': 'cross-site'})
    assert response.status_code == 403, response.text


@pytest.mark.parametrize('status,empty', [(200, True), (503, False), (429, False), (403, False)])
def test_empty_and_total_failure_are_distinct(customer, monkeypatch, status, empty):
    cable_company(customer)
    install_ted(monkeypatch, customer, payload={'notices': []} if empty else None, status=status)
    response = customer.client.post(customer.base('/discover/tenders'))
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['items'] == []
    assert report['total_failure'] is (status != 200)
    assert report['successful_sources'] == (['ted'] if empty else [])


def test_late_company_change_returns_conflict(customer, monkeypatch):
    cable_company(customer)
    other = customer.create_company('SYNTHETIC other supplier', 'furniture')
    def switch():
        customer.companies.set_active_for_organization(customer.owner.id, customer.organization.id, other['id'])
    install_ted(monkeypatch, customer, after_fetch=switch)
    response = customer.client.post(customer.base('/discover/tenders'))
    assert response.status_code == 409, response.text


def test_late_membership_revocation_is_denied(customer, monkeypatch):
    cable_company(customer)
    customer.as_account(customer.member)
    def revoke():
        customer.organizations.repository.remove_membership(customer.organization.id, customer.member.id)
    install_ted(monkeypatch, customer, after_fetch=revoke)
    assert customer.client.post(customer.base('/discover/tenders')).status_code == 403


def test_partial_failure_preserves_ted_results(customer):
    from app.sources.multi import MultiSourceFetchReport, SourceFailure
    from app.sources.ted_api import parse_ted_search_response
    cable_company(customer)
    class PartialCatalog(workflows.FakeCatalog):
        async def fetch(self, **kwargs):
            report = await super().fetch(**kwargs)
            return MultiSourceFetchReport(notices=report.notices,
                failures=(SourceFailure('uk_fts', 'SyntheticUnavailable', 'Synthetic failure'),),
                attempted_sources=('ted', 'uk_fts'), successful_sources=('ted',), statuses=())
    customer.client.app.state.runtime.source_catalog = PartialCatalog(parse_ted_search_response(fixture_payload()))
    response = customer.client.post(customer.base('/discover/tenders'))
    assert response.status_code == 200, response.text
    assert response.json()['partial_failure'] and not response.json()['total_failure']
    assert response.json()['failed_sources'] == ['uk_fts']
    assert len(response.json()['items']) == 2


def test_profile_edit_rejects_old_saved_preview(customer, monkeypatch):
    company = cable_company(customer)
    install_ted(monkeypatch, customer)
    item = customer.client.post(customer.base('/discover/tenders')).json()['items'][0]
    changed = dict(company['profile'], max_contract_value=500)
    assert customer.client.patch(customer.base(f"/companies/{company['id']}"), json={'profile': changed}).status_code == 200
    customer.client.app.state.runtime.tender_repository = ScopedMemorySaved(customer)
    assert customer.client.post(customer.base('/shortlist'), json=item).status_code == 409


def test_offline_probe_zero_http_and_honest_fixture_counts(monkeypatch):
    monkeypatch.setattr('scripts.phase24_customer_acceptance_probe.ted_catalog',
                        lambda: pytest.fail('offline attempted network catalog'))
    report, code = asyncio.run(probe())
    assert code == 0 and report['outbound_calls'] == 0 and report['real_results_count'] == 0
    assert report['fixture_results_count'] == report['synthetic_profile_evaluations'] == 3
    assert report['matching_count'] == 2 and report['excluded_count'] == 1
    assert report['unknown_data_count'] > 0 and not report['full_ai_analyzed']


@pytest.mark.parametrize('status', [200, 403, 429, 503])
def test_live_probe_one_request_budget_with_mock_transport(monkeypatch, status):
    calls = []
    def respond(request):
        calls.append(request)
        assert request.url.host == 'api.ted.europa.eu'
        return httpx.Response(status, json=fixture_payload())
    monkeypatch.setattr('app.sources.ted_api.source_client',
                        lambda **kwargs: source_client(**kwargs, transport=httpx.MockTransport(respond)))
    report, code = asyncio.run(probe(live=True))
    assert len(calls) == report['outbound_calls'] == 1
    assert code == (0 if status == 200 else 1)
    assert report['status'] == ('LIVE_VERIFIED' if status == 200 else 'UNAVAILABLE')
    # This invocation is mocked evidence even though it exercises the --live code path.


@pytest.mark.parametrize('payload', [{'notices': []}, {'unexpected': []}])
def test_live_probe_empty_or_invalid_response_never_passes(monkeypatch, payload):
    monkeypatch.setattr('app.sources.ted_api.source_client',
        lambda **kwargs: source_client(**kwargs, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload))))
    report, code = asyncio.run(probe(live=True))
    assert code == 1 and report['status'] == 'UNAVAILABLE'
    assert report['real_results_count'] == report['synthetic_profile_evaluations'] == 0
    assert report['outbound_calls'] == 1 and report['reason']


def test_live_probe_network_failure_is_safe_unavailable(monkeypatch):
    def fail(request):
        raise httpx.ConnectError('Synthetic transport failure', request=request)
    monkeypatch.setattr('app.sources.ted_api.source_client',
        lambda **kwargs: source_client(**kwargs, transport=httpx.MockTransport(fail)))
    report, code = asyncio.run(probe(live=True))
    assert code == 1 and report['status'] == 'UNAVAILABLE'
    assert report['outbound_calls'] == 1 and report['examples'] == []
    assert 'Synthetic transport failure' not in str(report)
