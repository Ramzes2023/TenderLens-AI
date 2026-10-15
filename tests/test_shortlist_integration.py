"""Real authentication, company switching and SQLite; no external APIs."""
import pytest
import tests.test_organization_companies as company_tests
from app.database.repository import TenderRepository


@pytest.fixture
def workspace():
    helper = company_tests.OrganizationCompanyApiTests()
    helper.setUp()
    try:
        repo = TenderRepository(helper.path)
        repo.initialize()
        helper.client.app.state.runtime.tender_repository = repo
        helper.as_account(helper.owner)
        yield helper
    finally:
        helper.doCleanups()


def test_shortlist_real_api_company_switch_and_security(workspace):
    w = workspace
    client = w.client
    base = f'/api/v1/organizations/{w.organization.id}/shortlist'
    def create(name):
        response = client.post(w.url(), json={'name': name, 'profile': w.profile(name)})
        assert response.status_code == 201
        return response.json()['id']
    def activate(company):
        assert client.post(w.url(f'/{company}/activate')).status_code == 200
    assert client.get(base).status_code == 409
    a, b = create('Company A'), create('Company B')
    activate(a)
    payload = dict(source='ted', external_id='acceptance-1', title='Valve supply',
                   url='https://example.com/tender', reasons=[], metadata_analysis={},
                   preliminary_scoring=dict(profile_name='A', profile_version='test',
                       fit_score=None, scorable_weight=0, completeness_percent=0, criteria=[]))
    saved = client.post(base, json=payload)
    assert saved.status_code == 200
    record = saved.json()
    assert record['company_id'] == a
    assert client.post(base, json=payload).json()['id'] == record['id']
    assert client.get(base).json() == [record]
    activate(b)
    assert client.get(base).json() == []
    assert client.delete(f"{base}/{record['id']}").status_code == 404
    activate(a)
    assert client.get(base).json()[0]['id'] == record['id']
    assert client.post(base, json=payload, headers={'Origin': 'https://evil.example'}).status_code == 403
    w.as_account(w.viewer)
    assert client.post(base, json=payload).status_code == 403
    assert client.delete(f"{base}/{record['id']}").status_code == 403
    w.as_account(w.outsider)
    assert client.get(base).status_code == 403
    w.as_account(w.owner)
    assert client.delete(f"{base}/{record['id']}").status_code == 204
    assert client.get(base).json() == []
    client.cookies.clear()
    assert client.get(base).status_code == 401
