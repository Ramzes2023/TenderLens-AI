"""Offline fixed-population retrieval and compatibility regressions."""
import sqlite3

import pytest

from app.analytics.paging import CursorError, seal, unseal, utc_filter
from app.database.repository import DatabaseAuthorizationError, DatabaseError
from tests.test_discovery_history_repository import _prepare_scope, _record
from tests.test_discovery_history_api_behavior import workspace, _snapshot
from tests.test_scoring_workers import system, enqueue, run


def test_over_100_equal_times_concurrent_insert_and_deletion(tmp_path):
    repo = _prepare_scope(tmp_path / 'paging.db')
    ids = [_record(repo, company_id=33, result_count=0, snapshot='{}').id for _ in range(123)]
    with sqlite3.connect(repo.path) as conn:
        conn.execute("UPDATE discovery_search_history SET created_at='2026-01-01T00:00:00+00:00'")
    page = repo.page_discovery_history(101, 7, 33, page_size=7)
    seen = [r.id for r in page['records']]
    later = _record(repo, company_id=33, result_count=0, snapshot='{}')
    with sqlite3.connect(repo.path) as conn:
        conn.execute("UPDATE discovery_search_history SET created_at='2026-01-01T00:00:00+00:00' WHERE id=?", (later.id,))
    while page['has_more']:
        page = repo.page_discovery_history(101, 7, 33, page_size=7, state=page['state'])
        seen.extend(r.id for r in page['records'])
    assert seen == list(reversed(ids))
    assert page['observed_count'] == page['state']['read_count'] == 123
    assert len(repo.list_discovery_search_history_for_organization(101, 7, 33)) == 50
    assert len(repo.list_discovery_search_history_for_organization(101, 7, 33, 999)) == 100
    with sqlite3.connect(repo.path) as conn:
        conn.execute('DELETE FROM discovery_search_history WHERE id=?', (ids[0],))
    assert repo.page_discovery_history(101, 7, 33, state=page['state'])['completeness'] == 'incomplete_deleted_events'


@pytest.mark.parametrize('role', ['owner', 'member', 'viewer'])
def test_membership_and_boundaries(tmp_path, role):
    repo = _prepare_scope(tmp_path / 'auth.db')
    with sqlite3.connect(repo.path) as conn:
        conn.execute('UPDATE organization_members SET role=?', (role,))
    _record(repo, company_id=33, result_count=0, snapshot='{}')
    with sqlite3.connect(repo.path) as conn:
        conn.execute("UPDATE discovery_search_history SET created_at='2026-01-01T00:00:00+00:00'")
    assert repo.page_discovery_history(101, 7, 33, start=utc_filter('2026-01-01T00:00:00Z'), end=utc_filter('2026-01-02T00:00:00Z'))['observed_count'] == 1
    assert repo.page_discovery_history(101, 7, 33, end=utc_filter('2026-01-01T00:00:00Z'))['observed_count'] == 0
    assert repo.page_discovery_history(101, 7, 33, start=utc_filter('2026-01-01T00:00:00.1Z'))['observed_count'] == 0
    for account, org, company in [(999, 7, 33), (101, 8, 33), (101, 7, 999)]:
        with pytest.raises(DatabaseAuthorizationError):
            repo.page_discovery_history(account, org, company)
    with sqlite3.connect(repo.path) as conn:
        conn.execute('DELETE FROM organization_members')
    with pytest.raises(DatabaseAuthorizationError):
        repo.page_discovery_history(101, 7, 33)


def test_signed_cursor_uses_existing_test_app_key(workspace):
    w, repo = workspace
    key = w.client.app.state.api_settings.api_key
    state = {'binding': ['history', 1, 7, 33], 'expires': 9999999999}
    token = seal(state, key)
    assert unseal(token, key, state['binding']) == state
    assert unseal(token, key, state['binding']) == state  # safe read replay
    for wrong in [['history', 2, 7, 33], ['history', 1, 7, 44], ['history', 1, 8, 33]]:
        with pytest.raises(CursorError):
            unseal(token, key, wrong)
    with pytest.raises(CursorError):
        unseal(token[:-2] + 'xx', key, state['binding'])
    with pytest.raises(CursorError):
        unseal(seal(dict(state, expires=0), key), key, state['binding'])


def test_history_api_corrupt_snapshot_and_legacy(workspace):
    w, repo = workspace
    company = w.client.post(w.url(), json={'name': 'Paging company', 'profile': w.profile('Paging company')}).json()['id']
    for snapshot in [_snapshot(), '{broken', '']:
        # Empty snapshots are rejected on writes; simulate damaged persisted bytes below.
        record = repo.record_discovery_search_for_organization(account_id=w.owner.id, organization_id=w.organization.id,
            company_id=company, result_count=0, scored_count=0, attempted_sources_json='[]',
            successful_sources_json='[]', failed_sources_json='[]', partial_failure=False,
            total_failure=False, snapshot_json=snapshot or '{}')
        if not snapshot:
            with sqlite3.connect(repo.path) as conn:
                conn.execute("UPDATE discovery_search_history SET snapshot_json='' WHERE id=?", (record.id,))
    base = f'/api/v1/organizations/{w.organization.id}/companies/{company}/discovery/history-page'
    result = w.client.get(base)
    assert result.status_code == 200, result.text
    assert {i['snapshot_state'] for i in result.json()['items']} == {'available', 'corrupt', 'missing'}
    assert result.json()['lifetime_total'] is None
    token = result.json()['population_cursor']
    batch = base.replace('history-page', 'history-snapshots')
    detail = w.client.get(batch, params={'population_cursor': token, 'ids': f'{record.id},{record.id},999999'})
    assert detail.status_code == 200, detail.text
    assert [i['state'] for i in detail.json()['items']] == ['missing', 'duplicate_request', 'missing_in_authorized_scope']
    another = w.client.post(w.url(), json={'name': 'Other paging', 'profile': w.profile('Other paging')}).json()['id']
    assert w.client.get(base.replace(f'companies/{company}', f'companies/{another}'), params={'cursor': token}).status_code == 422
    # Explicit company routes do not silently adopt the newly active company.
    assert w.client.get(base).json()['observed_count'] == 3
    for actor in [w.owner, w.member, w.viewer]:
        w.as_account(actor)
        assert w.client.get(base).status_code == 200
    w.as_account(w.outsider)
    assert w.client.get(base).status_code == 403
    w.client.cookies.clear()
    assert w.client.get(base).status_code == 401
    w.as_account(w.viewer)
    viewer_token = w.client.get(base).json()['population_cursor']
    with sqlite3.connect(repo.path) as conn:
        conn.execute('DELETE FROM organization_members WHERE organization_id=? AND account_id=?',
                     (w.organization.id, w.viewer.id))
    assert w.client.get(base, params={'cursor': viewer_token}).status_code == 403
    w.as_account(w.owner)
    assert w.client.get(base, params={'page_size': 100}).status_code == 422
    with sqlite3.connect(repo.path) as conn:
        conn.execute('DROP TABLE discovery_search_history')
    assert w.client.get(base).status_code == 503


def test_scoring_manifest_and_revision_provenance(system):
    s = system
    first = enqueue(s)
    assert run(s)
    page = s.service.list_page(scope=s.scope, page_size=1)
    assert page['observed_count'] == 1
    assert page['items'][0]['job_id'] == first.id
    revisions = s.service.revision_page(first.id, scope=s.scope)
    assert revisions['candidate_limit'] == 500
    assert revisions['revisions'][0]['notice']['external_id'] == 'one'
    assert revisions['revisions'][0]['calculation_time_kind'] == 'fenced_materialization'
    from app.jobs import JobScope
    other = JobScope(s.accounts[1].id, s.org.id, s.company.id)
    assert s.service.list_page(scope=other)['observed_count'] == 0
    second = enqueue(s, limit_per_source=2)
    first_page = s.service.list_page(scope=s.scope, page_size=1)
    enqueue(s, limit_per_source=3)
    second_page = s.service.list_page(scope=s.scope, page_size=1, state=first_page['state'])
    assert {i['job_id'] for i in first_page['items'] + second_page['items']} == {first.id, second.id}
    assert not second_page['has_more']
    with s.database.connect() as conn:
        conn.execute("UPDATE scoring_public_revisions SET notice_json='{corrupt'")
    assert s.service.revision_page(first.id, scope=s.scope)['revisions'][0]['storage_state'] == 'missing_or_corrupt_revision'


def test_run_api_authorization_no_get_mutations(system):
    from fastapi.testclient import TestClient
    from app.api.config import ApiSettings
    from app.api.main import create_app
    from app.api.runtime import ApiRuntime
    from app.api.security import SESSION_COOKIE
    from app.companies import CompanyService
    from app.organizations import OrganizationService
    from unittest.mock import patch
    s = system
    job = enqueue(s)
    assert run(s)
    runtime = ApiRuntime(auth_service=s.auth, scoring_run_service=s.service,
                         company_service=CompanyService(s.companies), organization_service=OrganizationService(s.orgs))
    app = create_app(runtime=runtime, settings=ApiSettings(host='127.0.0.1', port=8000, reload=False, api_key='fixture'))
    path = f'/api/v1/organizations/{s.org.id}/companies/{s.company.id}/scoring/runs'
    with TestClient(app) as client, patch('app.scoring.runs.score_metadata_preview', side_effect=AssertionError('GET must not score')):
        assert client.get(path).status_code == 401
        for account in s.accounts[:4]:
            client.cookies.set(SESSION_COOKIE, s.auth.create_session(account))
            result = client.get(path)
            assert result.status_code == 200, result.text
            assert result.json()['observed_count'] == (1 if account == s.accounts[0] else 0)
            assert client.get(path + '/' + job.id + '/revisions').status_code == (200 if account == s.accounts[0] else 403)
        client.cookies.set(SESSION_COOKIE, s.auth.create_session(s.accounts[4]))
        assert client.get(path).status_code == 403
        client.cookies.set(SESSION_COOKIE, s.auth.create_session(s.accounts[0]))
        assert client.get(path.replace(f'companies/{s.company.id}', f'companies/{s.second_company.id}')).json()['observed_count'] == 0
        assert client.get(path, params={'cursor': 'tampered'}).status_code == 422
        with s.database.connect() as conn:
            assert conn.execute('SELECT COUNT(*) FROM durable_jobs').fetchone()[0] == 1
            assert conn.execute('SELECT COUNT(*) FROM scoring_results').fetchone()[0] == 1
            conn.execute('DELETE FROM organization_members WHERE organization_id=? AND account_id=?', (s.org.id, s.accounts[0].id))
        assert client.get(path).status_code == 403
