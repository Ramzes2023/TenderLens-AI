"""Real offline HTTP/queue route with an explicitly composed existing service.

Production build_runtime remains unwired: its composition file is outside scope.
"""
import json
from contextlib import closing
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.security import SESSION_COOKIE
from app.companies import CompanyService
from app.jobs import JobService
from app.organizations import OrganizationService
from app.scoring.runs import ScoringRunService
from app.sources.catalog import build_source_catalog
from app.sources.eis_223_rss import parse_eis_223_feed
from test_ru03_integration import RSS, URL, enabled, settings
from test_scoring_workers import offline, system, run


@pytest.mark.parametrize('configuration,accepted', [
    ({}, False),
    ({'eis_223_rss_urls': (URL,)}, False),
    ({'eis_223_enabled': True}, False),
    ({'eis_223_enabled': True, 'eis_223_rss_urls': (URL,)}, True),
    ({'eis_223_enabled': True, 'eis_223_profile_feeds_enabled': True}, True),
])
def test_real_route_activation_and_isolation(system, configuration, accepted):
    s = system
    s.store.initialize()
    notice = parse_eis_223_feed(RSS, feed_url=URL)[0]
    s.store.upsert(notice, 'connector-sync-v1:eis_223:adapter-r1')
    s.store.upsert(replace(notice, source='eis'), 'connector-sync-v1:eis:adapter-r1')
    catalog = build_source_catalog(settings(**configuration))
    service = ScoringRunService(JobService(s.jobs), catalog=catalog)
    runtime = ApiRuntime(auth_service=s.auth, scoring_run_service=service,
                         source_catalog=catalog, company_service=CompanyService(s.companies),
                         organization_service=OrganizationService(s.orgs))
    app = create_app(runtime=runtime, settings=ApiSettings(
        host='127.0.0.1', port=8000, reload=False, api_key='fixture'))
    path = f'/api/v1/organizations/{s.org.id}/companies/{s.company.id}/scoring/runs'
    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE, s.auth.create_session(s.accounts[0]))
        selected = client.post(path, json={'sources': ['eis_223']})
        assert selected.status_code == (202 if accepted else 409), selected.text
        # Catalog activation never changes the customer's default selection.
        default = client.post(path, json={})
        route44 = client.post(path, json={'sources': ['eis']})
        assert default.status_code == route44.status_code == 202
        assert client.post(path, json={'sources': ['eis_223', 'eis_223']}).status_code == 409
        assert client.post(path, json={'sources': ['eis_223'], 'limit_per_source': 101}).status_code == 422
        while run(s):
            pass
        for response, source in [(default, 'ted'), (route44, 'eis')] + (
                [(selected, 'eis_223')] if accepted else []):
            job_id = response.json()['job_id']
            view = client.get(path + '/' + job_id)
            assert view.status_code == 200
            assert view.json()['complete'] and view.json()['candidate_count'] == 1
            assert view.json()['source_state'] == {source: 'available'}
            with closing(s.database.connect()) as conn:
                configuration_json = conn.execute(
                    'SELECT configuration_json FROM scoring_snapshots WHERE identity=?',
                    (response.json()['snapshot_id'],)).fetchone()[0]
            assert json.loads(configuration_json)['sources'] == [source]
            other_company = path.replace(f'companies/{s.company.id}', f'companies/{s.second_company.id}')
            assert client.get(other_company + '/' + job_id).status_code == 403
        if accepted:
            assert client.post(path, json={'sources': ['eis_223']}).json()['job_id'] == selected.json()['job_id']
        client.cookies.set(SESSION_COOKIE, s.auth.create_session(s.accounts[4]))
        assert client.post(path, json={'sources': ['eis_223']}).status_code == 403
        assert client.get(path + '/' + default.json()['job_id']).status_code == 403
    assert service.catalog is catalog


def test_missing_service_catalog_fails_closed_even_with_runtime_catalog(system):
    s = system
    runtime = ApiRuntime(auth_service=s.auth, scoring_run_service=s.service,
                         source_catalog=enabled(), company_service=CompanyService(s.companies),
                         organization_service=OrganizationService(s.orgs))
    app = create_app(runtime=runtime, settings=ApiSettings(
        host='127.0.0.1', port=8000, reload=False, api_key='fixture'))
    path = f'/api/v1/organizations/{s.org.id}/companies/{s.company.id}/scoring/runs'
    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE, s.auth.create_session(s.accounts[0]))
        assert client.post(path, json={'sources': ['eis_223']}).status_code == 409
    assert s.service.catalog is None
