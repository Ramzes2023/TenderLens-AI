"""OFFLINE_FIXTURE layered acceptance: real auth/routes, disposable SQLite, no live HTTP.

Saved double and TestClient are never reported as PostgreSQL/browser acceptance.
"""
import copy

import pytest

from scripts import phase24_v6_customer_browser_acceptance as v6


@pytest.fixture
def customer():
    with v6.isolated_customer() as instance:
        yield instance


def criterion(row, code):
    return next(c for c in row['scoring']['criteria'] if c['code'] == code)


def test_two_profile_matrix_has_explained_positive_negative_unknown_and_currency_stop(customer):
    rows = v6.evaluation_matrix()
    assert len(rows) == 10  # parser deduplicates six input rows to five identities
    cable = {r['external_id']: r for r in rows if 'cable supplier' in r['company']}
    accounting = {r['external_id']: r for r in rows if 'accounting vendor' in r['company']}
    assert cable['240001-2099']['prefilter_matched']
    assert not cable['240002-2099']['prefilter_matched']
    assert accounting['240002-2099']['prefilter_matched']
    assert not accounting['240001-2099']['prefilter_matched']
    for good in (cable['240001-2099'], accounting['240002-2099']):
        assert criterion(good, 'category')['status'] == 'matched'
        assert criterion(good, 'category')['explanation']
        assert criterion(good, 'documents')['status'] == 'not_scored'
    assert criterion(cable['240003-2099'], 'budget')['status'] == 'not_scored'
    assert criterion(cable['240004-2099'], 'budget')['status'] == 'failed'
    assert cable['240004-2099']['scoring']['stop_factors']
    assert criterion(cable['240002-2099'], 'category')['status'] == 'failed'
    assert all(r['evidence'] == 'OFFLINE_FIXTURE' for r in rows)


def test_real_login_find_save_saved_switch_roles_and_tenant_isolation(customer):
    result = v6.journey(customer)
    assert result['items'] >= 2
    assert result['second_company_items'] == 1
    assert result['storage'] == 'SCOPED_MEMORY_DOUBLE_NOT_POSTGRESQL'


def test_login_requires_verification_and_password_then_server_issues_session(customer):
    client = customer.client
    credentials = {'email': customer.owner.email, 'password': customer.password}
    assert client.post('/api/v1/auth/login', json=credentials).status_code == 403
    assert client.post('/api/v1/auth/login', json=dict(credentials, password='wrong password value')).status_code == 401
    v6.login(customer, customer.owner)
    assert client.get('/api/v1/auth/me').status_code == 200
    client.cookies.clear()
    assert client.get('/api/v1/auth/me').status_code == 401


@pytest.mark.parametrize('change,expected', [('company', 409), ('role', 403)])
def test_find_rechecks_context_after_transport(customer, change, expected):
    v6.login(customer, customer.member)
    v6.create_company(customer)
    second = v6.create_company(customer, 1)
    switched = False

    def switch_once():
        nonlocal switched
        if switched:
            return
        switched = True
        if change == 'company':
            customer.companies.set_active_for_organization(customer.member.id, customer.organization.id, second['id'])
        else:
            customer.organizations.repository.remove_membership(customer.organization.id, customer.member.id)

    with v6.offline_sources(customer, after_fetch=switch_once):
        response = customer.client.post(customer.base('/discover/tenders'))
    assert switched
    assert response.status_code == expected


def test_scoped_context_is_not_taken_from_headers_or_cross_tenant_ids(customer):
    v6.login(customer, customer.owner)
    company = v6.create_company(customer)
    second_org = customer.client.post('/api/v1/organizations',
        json={'name': 'SYNTHETIC empty tenant ' + customer.run_id}).json()['id']
    base = f'/api/v1/organizations/{second_org}'
    with v6.offline_sources(customer) as calls:
        assert customer.client.post(base + '/discover/tenders',
            headers={'X-Company-Id': str(company['id']), 'X-Organization-Id': str(customer.organization.id)}).status_code == 409
        assert customer.client.get(base + f"/companies/{company['id']}").status_code == 404
        assert not calls
    v6.login(customer, customer.outsider)
    assert customer.client.post(customer.base('/discover/tenders'),
        headers={'X-Account-Id': str(customer.owner.id)}).status_code == 403


def test_unknown_fields_stay_null_and_cross_site_save_has_no_effect(customer):
    from tests.test_phase24_customer_acceptance import ScopedMemorySaved
    v6.login(customer, customer.owner)
    v6.create_company(customer)
    with v6.offline_sources(customer):
        report = customer.client.post(customer.base('/discover/tenders')).json()
    item = next(i for i in report['items'] if i['external_id'] == '240003-2099')
    assert item['initial_price'] is None and item['deadline'] is None
    assert item['full_analysis'] is None and item['full_scoring'] is None
    storage = ScopedMemorySaved(customer)
    customer.client.app.state.runtime.tender_repository = storage
    assert customer.client.post(customer.base('/shortlist'), json=item,
        headers={'Origin': 'https://evil.example', 'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    assert not storage.rows
    forged = copy.deepcopy(item)
    forged['preliminary_provenance']['company_id'] += 100000
    assert customer.client.post(customer.base('/shortlist'), json=forged).status_code == 409
    assert not storage.rows


def test_total_transport_failure_does_not_become_empty_success(customer):
    v6.login(customer, customer.owner)
    v6.create_company(customer)
    with v6.offline_sources(customer, ted_status=503) as calls:
        response = customer.client.post(customer.base('/discover/tenders'))
    assert response.status_code == 200
    assert response.json()['total_failure']
    assert response.json()['items'] == []
    assert response.json()['successful_sources'] == []
    assert {host for _, host in calls} == {'api.ted.europa.eu', 'www.find-tender.service.gov.uk'}


def test_harness_stdout_never_promotes_layered_pass_to_authenticated_browser(capsys):
    v6.stdout_status({'API_E2E': 'NOT_VERIFIED', 'BROWSER_AUTHENTICATED': 'NOT_VERIFIED', 'layered_api': 'PASS'})
    output = capsys.readouterr().out
    assert 'V6_AUTHENTICATED_API=NOT_VERIFIED' in output
    assert 'V6_AUTHENTICATED_BROWSER=NOT_VERIFIED' in output
    assert 'V6_REAL_TED_IN_THIS_RUN=NO' in output
    assert 'V6_LIVE_PRIOR_EVIDENCE=5_NOT_REPROBED' in output
