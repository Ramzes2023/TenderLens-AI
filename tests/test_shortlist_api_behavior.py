import asyncio

def _run(coro):
    return asyncio.run(coro)
from types import SimpleNamespace
import pytest
from fastapi import HTTPException, Response
import app.api.organization_workflow_routes as routes
from app.companies import CompanyAuthorizationError

class FakeRepository:

    def __init__(self):
        self.saved_calls = []
        self.list_calls = []
        self.delete_calls = []
        self.next_id = 1
        self.saved_by_scope = {}

    def save_opportunity_for_organization(self, **kwargs):
        self.saved_calls.append(dict(kwargs))
        key = (kwargs['organization_id'], kwargs['company_id'], kwargs['source'], kwargs['external_id'])
        record = self.saved_by_scope.get(key)
        if record is None:
            record = SimpleNamespace(id=self.next_id, organization_id=kwargs['organization_id'], company_id=kwargs['company_id'], source=kwargs['source'], external_id=kwargs['external_id'], snapshot_json=kwargs['snapshot_json'], created_at='2026-10-06T12:00:00', updated_at='2026-10-06T12:00:00')
            self.saved_by_scope[key] = record
            self.next_id += 1
        return record

    def list_saved_opportunities_for_organization(self, account_id, organization_id, company_id, limit):
        self.list_calls.append((account_id, organization_id, company_id, limit))
        return [record for key, record in self.saved_by_scope.items() if key[0] == organization_id and key[1] == company_id]

    def delete_saved_opportunity_for_organization(self, **kwargs):
        self.delete_calls.append(dict(kwargs))
        for key, record in list(self.saved_by_scope.items()):
            if key[0] == kwargs['organization_id'] and key[1] == kwargs['company_id'] and (record.id == kwargs['saved_id']):
                del self.saved_by_scope[key]
                return True
        return False

class FakePayload:

    def __init__(self, source='eis', external_id='notice-1', title='Supply of industrial pumps'):
        self.source = source
        self.external_id = external_id
        self.title = title

    def model_dump_json(self):
        return f'{{"source":"{self.source}","external_id":"{self.external_id}","title":"{self.title}"}}'

def install_route_stubs(monkeypatch, repository, company_ids):
    account = SimpleNamespace(id=7001)
    ids = iter(company_ids)

    async def fake_account(request):
        return account

    async def fake_active_company(request, current_account, organization_id):
        return SimpleNamespace(id=next(ids))
    guards = []

    def fake_same_origin(request):
        guards.append(True)
    monkeypatch.setattr(routes, '_account', fake_account)
    monkeypatch.setattr(routes, '_active_company', fake_active_company)
    monkeypatch.setattr(routes, '_shortlist_repository', lambda request: repository)
    monkeypatch.setattr(routes, 'require_same_origin_browser_request', fake_same_origin)
    monkeypatch.setattr(routes, '_saved_opportunity_response', lambda record: record)
    return (account, guards)

def test_shortlist_requires_source_and_external_id():
    fields = routes.TenderDiscoveryItem.model_fields
    assert fields['source'].is_required()
    assert fields['external_id'].is_required()
    assert 'company_id' not in fields

def test_shortlist_account_requires_authentication(monkeypatch):

    async def no_account(request):
        return None
    monkeypatch.setattr(routes, 'current_account', no_account)
    with pytest.raises(HTTPException) as error:
        _run(routes._account(SimpleNamespace()))
    assert error.value.status_code == 401

def test_active_company_maps_wrong_org_to_403():

    class DeniedCompanyService:

        def active_for_organization(self, account_id, organization_id):
            raise CompanyAuthorizationError('denied')
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(company_service=DeniedCompanyService()))))
    account = SimpleNamespace(id=7001)
    with pytest.raises(HTTPException) as error:
        _run(routes._active_company(request, account, 999))
    assert error.value.status_code == 403

def test_save_uses_backend_active_company(monkeypatch):
    repository = FakeRepository()
    account, guards = install_route_stubs(monkeypatch, repository, [101])
    response = Response()
    result = _run(routes.save_discovered_opportunity(organization_id=55, payload=FakePayload(), request=SimpleNamespace(), response=response))
    assert len(repository.saved_calls) == 1
    call = repository.saved_calls[0]
    assert call['account_id'] == account.id
    assert call['organization_id'] == 55
    assert call['company_id'] == 101
    assert call['source'] == 'eis'
    assert call['external_id'] == 'notice-1'
    assert guards == [True]
    assert response.headers['Cache-Control'] == 'no-store'
    assert result.company_id == 101

def test_duplicate_save_is_idempotent_in_same_scope(monkeypatch):
    repository = FakeRepository()
    install_route_stubs(monkeypatch, repository, [101, 101])
    first = _run(routes.save_discovered_opportunity(organization_id=55, payload=FakePayload(), request=SimpleNamespace(), response=Response()))
    second = _run(routes.save_discovered_opportunity(organization_id=55, payload=FakePayload(), request=SimpleNamespace(), response=Response()))
    assert first.id == second.id
    assert len(repository.saved_calls) == 2

def test_list_uses_active_company_and_no_store(monkeypatch):
    repository = FakeRepository()
    repository.save_opportunity_for_organization(account_id=7001, organization_id=55, company_id=101, source='eis', external_id='notice-1', snapshot_json='{}')
    repository.save_opportunity_for_organization(account_id=7001, organization_id=55, company_id=202, source='ted', external_id='notice-2', snapshot_json='{}')
    install_route_stubs(monkeypatch, repository, [101])
    response = Response()
    result = _run(routes.list_saved_opportunities(organization_id=55, request=SimpleNamespace(), response=response))
    assert repository.list_calls[-1] == (7001, 55, 101, 200)
    assert len(result) == 1
    assert result[0].company_id == 101
    assert response.headers['Cache-Control'] == 'no-store'

def test_delete_is_company_scoped_and_guarded(monkeypatch):
    repository = FakeRepository()
    record = repository.save_opportunity_for_organization(account_id=7001, organization_id=55, company_id=101, source='eis', external_id='notice-1', snapshot_json='{}')
    _, guards = install_route_stubs(monkeypatch, repository, [101])
    response = _run(routes.remove_saved_opportunity(organization_id=55, saved_id=record.id, request=SimpleNamespace()))
    assert response.status_code == 204
    assert response.headers['Cache-Control'] == 'no-store'
    assert guards == [True]
    call = repository.delete_calls[-1]
    assert call['organization_id'] == 55
    assert call['company_id'] == 101

def test_active_company_switch_changes_shortlist_scope(monkeypatch):
    repository = FakeRepository()
    install_route_stubs(monkeypatch, repository, [101, 202, 101, 202])
    _run(routes.save_discovered_opportunity(organization_id=55, payload=FakePayload(external_id='company-a'), request=SimpleNamespace(), response=Response()))
    _run(routes.save_discovered_opportunity(organization_id=55, payload=FakePayload(external_id='company-b'), request=SimpleNamespace(), response=Response()))
    response_a = Response()
    list_a = _run(routes.list_saved_opportunities(organization_id=55, request=SimpleNamespace(), response=response_a))
    response_b = Response()
    list_b = _run(routes.list_saved_opportunities(organization_id=55, request=SimpleNamespace(), response=response_b))
    assert [item.external_id for item in list_a] == ['company-a']
    assert [item.external_id for item in list_b] == ['company-b']

def test_missing_active_company_returns_409(monkeypatch):

    async def fake_account(request):
        return SimpleNamespace(id=7001)

    async def no_active_company(request, account, organization_id):
        return None
    monkeypatch.setattr(routes, '_account', fake_account)
    monkeypatch.setattr(routes, '_active_company', no_active_company)
    monkeypatch.setattr(routes, 'require_same_origin_browser_request', lambda request: None)
    with pytest.raises(HTTPException) as error:
        _run(routes.save_discovered_opportunity(organization_id=55, payload=FakePayload(), request=SimpleNamespace(), response=Response()))
    assert error.value.status_code == 409
