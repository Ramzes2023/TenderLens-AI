"""Real HTTP/session/SQLite proofs; independently enumerated fixture identities."""
import json
import sqlite3
from unittest.mock import patch
import pytest

from tests.test_discovery_history_api_behavior import workspace
from tests.test_analytics_service import item
from app.analytics.paging import seal, unseal


@pytest.fixture
def analytics(workspace):
    w, repo = workspace
    company = w.client.post(w.url(), json={'name': 'Analytics', 'profile': w.profile('Analytics')}).json()['id']
    items = [item('a', 0), item('b', 35, countries=('IT', 'FR')), item('c', 65), item('d', 90), item('e', None)]
    for entry in items:
        entry['preliminary_provenance']['organization_id'] = w.organization.id
        entry['preliminary_provenance']['company_id'] = company
    def persist(entries=items, **overrides):
        values = dict(account_id=w.owner.id, organization_id=w.organization.id, company_id=company,
            result_count=len(entries), scored_count=0, snapshot_json=json.dumps({'items': entries}),
            attempted_sources_json='["ted"]', successful_sources_json='["ted"]', failed_sources_json='[]',
            partial_failure=False, total_failure=False)
        values.update(overrides)
        return repo.record_discovery_search_for_organization(**values)
    record = persist()
    base = f'/api/v1/organizations/{w.organization.id}/companies/{company}/analytics/v1'
    return w, repo, company, base, persist, record


def get(w, base, route='history/aggregate', **params):
    return w.client.get(base + '/' + route, params=dict(timezone_name='Europe/Rome', **params))


def test_known_kpis_rows_filters_and_replay(analytics):
    w, repo, company, base, persist, record = analytics
    response = get(w, base, page_size=2)
    assert response.status_code == 200, response.text
    data = response.json()
    assert response.headers['cache-control'] == 'no-store'
    assert {key: value['value'] for key, value in data['kpis'].items()} == {
        'Discovered': 5, 'Matched': 3, 'High Fit': 2, 'Active Sources': 1, 'Countries': 2, 'Closing Soon': 0}
    assert data['population']['unknown_fit_count'] == 1
    assert data['population']['selected_event_ids'] == [record.id]
    rows = data['rows']
    while data['next_cursor']:
        response = get(w, base, 'history/rows', page_size=2, cursor=data['next_cursor'])
        assert response.status_code == 200, response.text
        data = response.json()
        rows.extend(data['rows'])
    assert [r['identity'] for r in rows] == [['ted', x] for x in 'abcde']
    assert len({r['row_id'] for r in rows}) == 5
    assert all(r['event_id'] == record.id for r in rows)
    replay = get(w, base, 'history/replay', page_size=2, population_token=data['population_token'])
    assert replay.status_code == 200
    assert replay.json()['rows'] == rows[:2]
    filtered = get(w, base, country='FR').json()
    assert [r['identity'] for r in filtered['rows']] == [['ted', 'b']]
    assert filtered['kpis']['Discovered']['value'] == filtered['total'] == 1
    assert filtered['kpis']['Matched']['identities'] == [['ted', 'b']]
    assert filtered['population']['union_count'] == 5
    top = get(w, base, order='top').json()
    assert [r['identity'] for r in top['rows']] == [['ted', x] for x in 'dcba']
    assert get(w, base, fit_band='high').json()['drilldowns']['Discovered'] == [['ted', 'c'], ['ted', 'd']]
    assert get(w, base, fit_band='unknown').json()['rows'][0]['identity'] == ['ted', 'e']
    assert get(w, base, kpi='Matched').json()['total'] == 3
    assert get(w, base, date_semantics='published_at', date_day='2026-03-01').json()['total'] == 5


@pytest.mark.parametrize('role', ['owner', 'member', 'viewer'])
@pytest.mark.parametrize('route', ['history/aggregate', 'history/rows', 'history/replay'])
def test_roles_and_revocation(analytics, role, route):
    w, repo, company, base, persist, record = analytics
    w.as_account(getattr(w, role))
    token = get(w, base).json()['population_token']
    assert get(w, base, route, population_token=token).status_code == 200
    with sqlite3.connect(repo.path) as conn:
        conn.execute('DELETE FROM organization_members WHERE organization_id=? AND account_id=?',
                     (w.organization.id, getattr(w, role).id))
    assert get(w, base, route, population_token=token).status_code == 403


@pytest.mark.parametrize('route', ['history/aggregate', 'history/rows', 'history/replay', 'capabilities/D', 'capabilities/R', 'capabilities/P'])
def test_denied_before_history_access(analytics, route):
    w, repo, company, base, persist, record = analytics
    with patch.object(repo, 'page_discovery_history', side_effect=AssertionError('unauthorized DB access')):
        w.as_account(w.outsider)
        assert get(w, base, route).status_code == 403
        w.client.cookies.clear()
        assert get(w, base, route).status_code == 401


@pytest.mark.parametrize('change', [dict(country='FR'), dict(timezone_name='UTC'), dict(start='2026-01-01T00:00:00Z'),
    dict(end='2027-01-01T00:00:00Z'), dict(deadline_days=8), dict(page_size=1), dict(order='top'),
    dict(fit_band='low'), dict(as_of='2026-01-01T00:00:00Z'), dict(policy='evil'), dict(ids='1')])
def test_token_query_binding(analytics, change):
    w, repo, company, base, persist, record = analytics
    token = get(w, base).json()['population_token']
    params = dict(timezone_name='Europe/Rome', population_token=token, **{k:v for k,v in change.items() if k != 'timezone_name'})
    params['timezone_name'] = change.get('timezone_name', 'Europe/Rome')
    assert w.client.get(base + '/history/replay', params=params).status_code == 422


def test_tampering_expiration_account_and_company_binding(analytics):
    w, repo, company, base, persist, record = analytics
    token = get(w, base).json()['population_token']
    assert get(w, base, population_token=token[:-5] + 'abcde').status_code == 422
    import base64
    state = json.loads(base64.urlsafe_b64decode(token + '=' * (-len(token) % 4))[32:])
    key = w.client.app.state.api_settings.api_key
    assert get(w, base, population_token=seal(dict(state, expires=0), key)).status_code == 422
    another = w.client.post(w.url(), json={'name':'Other', 'profile':w.profile('Other')}).json()['id']
    other_base = base.replace(f'companies/{company}', f'companies/{another}')
    assert get(w, other_base, population_token=token).status_code == 422
    # Explicit address is valid even after another company is made active.
    assert get(w, base).json()['total'] == 5
    w.as_account(w.member)
    assert get(w, base, population_token=token).status_code == 422
    assert get(w, base.replace(f'organizations/{w.organization.id}', 'organizations/99999')).status_code == 403
    assert get(w, base.replace(f'companies/{company}', 'companies/99999')).status_code == 404
    for invalid in ('-1', '0', '99999999999999999999999999999999'):
        assert get(w, base.replace(f'companies/{company}', 'companies/' + invalid)).status_code == 422
        assert get(w, base.replace(f'organizations/{w.organization.id}', 'organizations/' + invalid)).status_code == 422


@pytest.mark.parametrize('mutation', ['delete', 'body', 'metadata', 'corrupt'])
def test_snapshot_drift(analytics, mutation):
    w, repo, company, base, persist, record = analytics
    token = get(w, base).json()['population_token']
    with sqlite3.connect(repo.path) as conn:
        if mutation == 'delete':
            conn.execute('DELETE FROM discovery_search_history WHERE id=?', (record.id,))
        elif mutation == 'metadata':
            conn.execute('UPDATE discovery_search_history SET successful_sources_json=? WHERE id=?', ('[]', record.id))
        else:
            conn.execute('UPDATE discovery_search_history SET snapshot_json=? WHERE id=?',
                         ('{corrupt' if mutation == 'corrupt' else '{"items":[]}', record.id))
    assert get(w, base, population_token=token).status_code == 409
    if mutation == 'corrupt':
        assert get(w, base).status_code == 503


def test_large_equal_timestamp_history_fence_and_limits(analytics):
    w, repo, company, base, persist, record = analytics
    ids = [record.id] + [persist([]).id for _ in range(122)]
    with sqlite3.connect(repo.path) as conn:
        conn.execute('UPDATE discovery_search_history SET created_at=?', ('2026-03-01T00:00:00+00:00',))
    data = get(w, base).json()
    assert data['population']['selected_event_ids'] == list(reversed(ids))
    assert data['population']['observed_events'] == 123
    later = persist([item('new')])
    with sqlite3.connect(repo.path) as conn:
        conn.execute('UPDATE discovery_search_history SET created_at=? WHERE id=?', ('2026-03-01T00:00:00+00:00', later.id))
    replay = get(w, base, population_token=data['population_token'])
    assert replay.status_code == 200, replay.text
    assert replay.json()['population']['selected_event_ids'] == list(reversed(ids))
    assert [r['identity'] for r in replay.json()['rows']] == [['ted', x] for x in 'abcde']
    from app.api import analytics_routes
    with patch.object(analytics_routes, 'MAX_EVENTS', 100):
        assert get(w, base).status_code == 503


def test_no_writes_scoring_sources_or_secret_payloads(analytics):
    w, repo, company, base, persist, record = analytics
    with sqlite3.connect(repo.path) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        before = {t: conn.execute('SELECT * FROM "' + t + '"').fetchall() for t in tables}
    runtime = w.client.app.state.runtime
    class ForbiddenWork:
        def __getattr__(self, name):
            raise AssertionError('Analytics attempted source/scoring/job work: ' + name)
    runtime.tender_discovery_service = ForbiddenWork()
    runtime.scoring_run_service = ForbiddenWork()
    runtime.source_catalog = ForbiddenWork()
    with patch('app.api.analytics_routes.current_account', wraps=__import__('app.api.security', fromlist=['current_account']).current_account) as auth:
        response = get(w, base)
        assert response.status_code == 200
        assert all(call.kwargs == {'touch':False} for call in auth.call_args_list)
    with sqlite3.connect(repo.path) as conn:
        after = {t: conn.execute('SELECT * FROM "' + t + '"').fetchall() for t in tables}
    assert before == after
    text = response.text
    assert w.client.app.state.api_settings.api_key not in text
    assert 'metadata_analysis' not in text and 'full_scoring' not in text
    for origin in 'DRP':
        cap = get(w, base, 'capabilities/' + origin)
        # Capabilities have no filter query contract.
        assert cap.status_code == 200
        assert cap.json()['capability']['state'] == 'unavailable'


@pytest.mark.parametrize('params', [dict(page_size=0), dict(page_size=101), dict(start='2026-01-01'),
    dict(timezone_name=''), dict(deadline_days=0), dict(country='italy'), dict(date_day='bad'), dict(source='unknown')])
def test_invalid_input(analytics, params):
    w, repo, company, base, persist, record = analytics
    query = dict(timezone_name='Europe/Rome')
    query.update(params)
    assert w.client.get(base + '/history/aggregate', params=query).status_code == 422


def test_missing_timezone_storage_and_key(analytics):
    w, repo, company, base, persist, record = analytics
    assert w.client.get(base + '/history/aggregate').status_code == 422
    assert get(w, base, 'history/replay').status_code == 422
    w.client.app.state.runtime.tender_repository = None
    assert get(w, base).status_code == 503
    w.client.app.state.runtime.tender_repository = repo
    with sqlite3.connect(repo.path) as conn:
        conn.execute('DROP TABLE discovery_search_history')
    assert get(w, base).status_code == 503


def test_profile_drift_timezone_unavailable_and_source_failure(analytics):
    w, repo, company, base, persist, record = analytics
    result = get(w, base)
    assert result.status_code == 200
    assert {r['current_fit_reason'] for r in result.json()['rows'] if r['historical_fit_band'] != 'unknown'} == {'stale_profile_digest'}
    unknown_zone = w.client.get(base + '/history/aggregate', params={'timezone_name':'Unavailable/Zone'})
    assert unknown_zone.status_code == 200
    assert unknown_zone.json()['population']['timezone_available'] is False
    token = result.json()['population_token']
    changed = w.profile('Analytics')
    changed['product_keywords'] = ['changed']
    response = w.client.patch(w.url() + '/' + str(company), json={'profile':changed})
    assert response.status_code == 200, response.text
    assert get(w, base, population_token=token).status_code == 409
    persist([], failed_sources_json='["ted"]', successful_sources_json='[]', total_failure=True)
    failed = get(w, base).json()
    assert failed['kpis']['Discovered']['value'] is None
    assert failed['kpis']['Discovered']['numerator'] == 5
    assert failed['population']['source_search_coverage'] == 'partial_failed_searches'


def test_concurrent_mutation_and_revocation_before_return(analytics):
    w, repo, company, base, persist, record = analytics
    from app.api import analytics_routes
    original = analytics_routes.aggregate_history
    def revoke(*args, **kwargs):
        result = original(*args, **kwargs)
        with sqlite3.connect(repo.path) as conn:
            conn.execute('DELETE FROM organization_members WHERE account_id=? AND organization_id=?',
                         (w.viewer.id, w.organization.id))
        return result
    w.as_account(w.viewer)
    with patch.object(analytics_routes, 'aggregate_history', side_effect=revoke):
        assert get(w, base).status_code == 403
    w.as_account(w.owner)
    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        with sqlite3.connect(repo.path) as conn:
            conn.execute('UPDATE discovery_search_history SET successful_sources_json=? WHERE id=?', ('[]', record.id))
        return result
    with patch.object(analytics_routes, 'aggregate_history', side_effect=mutate):
        assert get(w, base).status_code == 409


def test_duplicate_conflicts_empty_storage_and_limits(analytics):
    w, repo, company, base, persist, record = analytics
    with sqlite3.connect(repo.path) as conn:
        conn.execute('DELETE FROM discovery_search_history')
    empty = get(w, base)
    assert empty.status_code == 200
    assert empty.json()['kpis']['Discovered']['value'] == 0
    repeated = item('x', 65)
    persist([repeated, repeated])
    result = get(w, base).json()
    assert result['total'] == 1
    assert result['population']['exclusions']['duplicate_within_event'] == 1
    persist([item('x', 35), item('x', 90)])
    result = get(w, base).json()
    assert result['total'] == 0
    assert result['kpis']['Discovered']['value'] is None
    from app.api import analytics_routes
    with patch.object(analytics_routes, 'MAX_ROWS', 1):
        assert get(w, base).status_code == 503
    with patch.object(analytics_routes, 'MAX_RESPONSE', 1):
        assert get(w, base).status_code == 503
    with patch.object(analytics_routes, 'MAX_SECONDS', 0):
        assert get(w, base).status_code == 503


def test_signing_unavailable_and_org_storage_error(analytics):
    w, repo, company, base, persist, record = analytics
    from app.organizations import OrganizationError
    with patch.object(w.client.app.state.runtime.organization_service, 'require_membership',
                      side_effect=OrganizationError('Organization storage operation failed.')):
        assert get(w, base).status_code == 503
    from app.database.backend import StorageError
    with patch.object(w.client.app.state.runtime.organization_service, 'require_membership',
                      side_effect=StorageError('private credential-bearing error payload')):
        response = get(w, base)
        assert response.status_code == 503
        assert 'credential' not in response.text
    settings = w.client.app.state.api_settings
    from dataclasses import replace
    try:
        w.client.app.state.api_settings = replace(settings, api_key='')
        assert get(w, base).status_code == 503
    finally:
        w.client.app.state.api_settings = settings


def test_real_deadline_country_category_predicate_identities(analytics):
    from datetime import datetime, timedelta, timezone
    w, repo, company, base, persist, record = analytics
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    a = item('instant', 65, deadline=tomorrow.isoformat(), categories=('45000000',))
    b = item('calendar', 35, deadline=(tomorrow + timedelta(days=1)).date().isoformat())
    for entry in (a, b):
        entry['preliminary_provenance']['organization_id'] = w.organization.id
        entry['preliminary_provenance']['company_id'] = company
    persist([a, b])
    data = get(w, base).json()
    assert data['kpis']['Closing Soon']['identities'] == [['ted', 'instant']]
    assert get(w, base, deadline='instant_closing_soon').json()['drilldowns']['Discovered'] == [['ted', 'instant']]
    assert get(w, base, deadline='local_date_closing_soon').json()['drilldowns']['Discovered'] == [['ted', 'calendar']]
    filtered = get(w, base, category='cpv-2008/45000000', country='IT', fit_band='high').json()
    assert filtered['total'] == filtered['kpis']['High Fit']['value'] == 1
    assert filtered['rows'][0]['identity'] == ['ted', 'instant']
    assert filtered['distributions']['categories'][0]['measure']['identities'] == [['ted', 'instant']]


def test_policy_redeploy_invalidates_commitments_and_repeated_parameters(analytics):
    w, repo, company, base, persist, record = analytics
    token = get(w, base).json()['population_token']
    from app.api import analytics_routes
    with patch.object(analytics_routes, 'VERSIONS', ['changed-policy']):
        assert get(w, base, population_token=token).status_code == 422
    assert w.client.get(base + '/history/aggregate', params=[('timezone_name','UTC'), ('timezone_name','Europe/Rome')]).status_code == 422


def test_budget_expiration_inside_last_database_read():
    from unittest.mock import Mock
    from fastapi import HTTPException
    from app.api.analytics_routes import BoundedHistory
    repository = Mock()
    reader = BoundedHistory(repository, None, 11)
    with patch('app.api.analytics_routes.time.monotonic', side_effect=[10, 12]):
        with pytest.raises(HTTPException) as error:
            reader.page_discovery_history()
    assert error.value.status_code == 503
    repository.page_discovery_history.assert_called_once()
