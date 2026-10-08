"""Offline production scoring path: real SQLite/auth/API/queue, fake public sources."""
import json
import sqlite3
import socket
import threading
import uuid
from contextlib import closing
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.security import SESSION_COOKIE
from app.auth import AuthRepository, AuthService
from app.companies import CompanyRepository, CompanyService
from app.database.backend import Database, postgres_sql
from app.database.config import DatabaseSettings
from app.database.import_sqlite import preflight_source
from app.database.migrations import MIGRATIONS
from app.jobs import HandlerRegistry, JobRepository, JobScope, JobService
from app.jobs.worker import ExecutionContext, PermanentJobError, RetryableJobError, Worker, main
from app.monitoring.service import prefilter_notice
from app.organizations import OrganizationRepository, OrganizationService
from app.scoring.engine import score_tender
from app.scoring.models import CompanyProfile
from app.scoring.preview import score_metadata_preview
from app.scoring.runs import (ENGINE_VERSION, JOB_TYPE, MAX_RESULTS, ScoringAccessError,
                              ScoringInputError, ScoringRunHandler, ScoringRunService)
from app.services.tender_analysis import analysis_from_notice
from app.sources.models import TenderNotice
from app.sources.opportunities import OpportunityRepository


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv('VALYQON_EMAIL_MODE', 'disabled')
    monkeypatch.setenv('VALYQON_AI_FALLBACK_ENABLED', 'false')
    original_connect = socket.socket.connect
    def local_connect(sock, address):
        # Windows asyncio uses a local socketpair to wake its event loop.
        if isinstance(address, tuple) and address[0] in {'127.0.0.1', '::1'}:
            return original_connect(sock, address)
        raise AssertionError('External network forbidden')
    with patch('socket.getaddrinfo', side_effect=AssertionError('External DNS forbidden')), \
         patch('socket.socket.connect', local_connect):
        yield


def notice(external_id='one', **kwargs):
    return replace(TenderNotice('ted', external_id, 'Supply of aluminium', 'https://example.test/tender',
                                summary='Aluminium products', currency='EUR', initial_price=100), **kwargs)


@pytest.fixture
def system(tmp_path):
    database = Database(DatabaseSettings('', tmp_path / 'scoring.db'))
    clock = SimpleNamespace(now=1800000000.0)
    jobs = JobRepository(database, clock=lambda: clock.now)
    jobs.initialize()
    auth_repo = AuthRepository(database)
    auth = AuthService(auth_repo)
    accounts = [auth_repo.create_account(f'{i}@example.test', 'synthetic-hash') for i in range(5)]
    orgs = OrganizationRepository(database)
    org = orgs.create('Scoring organization', accounts[0].id)
    for account, role in zip(accounts[1:4], ('admin', 'member', 'viewer')):
        orgs.add_membership(org.id, account.id, role)
    other_org = orgs.create('Other organization', accounts[4].id)
    companies = CompanyRepository(database)
    profile = CompanyProfile(profile_version='v1', company_name='Private company', product_keywords=['aluminium'],
                             accepted_currencies=['EUR'], max_contract_value=1000)
    company = companies.create_for_organization(account_id=accounts[0].id, organization_id=org.id,
                                                name='Private company', profile=profile)
    other_company = companies.create_for_organization(account_id=accounts[4].id, organization_id=other_org.id,
                                                      name='Other company', profile=profile)
    second_company = companies.create_for_organization(account_id=accounts[0].id, organization_id=org.id,
                                                       name='Second company', profile=profile)
    scope = JobScope(accounts[0].id, org.id, company.id)
    store = OpportunityRepository(database)
    store.upsert(notice(), 'connector-sync-v1:ted:adapter-r1')
    service = ScoringRunService(JobService(jobs))
    handler = ScoringRunHandler(service)
    registry = HandlerRegistry()
    registry.register(JOB_TYPE, handler)
    yield SimpleNamespace(**locals())
    database.close()


def enqueue(s, **kwargs):
    return s.service.enqueue(scope=s.scope, **kwargs)


def run(s):
    return Worker(s.jobs, s.registry, job_types=(JOB_TYPE,)).run_once()


def claim(s):
    return s.jobs.claim_next('worker-' + uuid.uuid4().hex, job_types=(JOB_TYPE,))


def context(s, claim):
    ctx = ExecutionContext(claim.job, threading.Event())
    ctx.fenced_write = lambda write: s.jobs.fenced_write(claim.job.id, claim.token, write)
    return ctx


def count(s):
    with closing(s.database.connect()) as conn:
        return conn.execute('SELECT COUNT(*) FROM scoring_results').fetchone()[0]


def test_actual_worker_parity_persistence_and_safe_contract(system):
    s = system
    job = enqueue(s)
    assert set(job.payload) == {'snapshot_id', 'profile_digest', 'engine_version'}
    assert s.service.view(job.id, scope=s.scope)['items'] == []
    assert run(s)
    result = s.service.view(job.id, scope=s.scope)
    expected = score_metadata_preview(analysis_from_notice(notice()), s.profile)
    assert result['items'][0]['scoring'] == expected.model_dump(mode='json', exclude={'profile_name', 'profile_version'})
    assert result['status'] == 'succeeded' and result['complete'] and result['result_count'] == 1
    assert s.jobs.get(job.id, scope=s.scope).result['result_count'] == 1
    assert count(s) == 1
    assert enqueue(s).id == job.id
    encoded = json.dumps([job.payload, s.jobs.get(job.id, scope=s.scope).result, result])
    for forbidden in ('Private company', 'product_keywords', 'notice_json', 'lease_token', 'summary', 'PDF', 'prompt'):
        assert forbidden not in encoded
    restarted = ScoringRunService(JobService(JobRepository(Database(s.database.settings))))
    assert restarted.view(job.id, scope=s.scope)['items'] == result['items']
    restarted.database.close()
    with closing(s.database.connect()) as conn:
        assert 'Private company' not in conn.execute('SELECT notice_json FROM source_opportunities').fetchone()[0]
        preflight_source(conn)


def test_profile_and_snapshot_changes_have_distinct_identity(system):
    s = system
    job = enqueue(s)
    s.clock.now += 1
    s.store.upsert(notice(title='Supply of aluminium revised'), 'connector-sync-v1:ted:adapter-r1')
    changed_snapshot = enqueue(s)
    assert changed_snapshot.id != job.id
    # Original snapshot survives mutation; worker still computes original metadata.
    assert run(s)
    old = s.service.view(job.id, scope=s.scope)
    assert old['items'][0]['scoring'] == score_metadata_preview(analysis_from_notice(notice()), s.profile).model_dump(
        mode='json', exclude={'profile_name', 'profile_version'})
    changed = s.profile.model_copy(update={'product_keywords': ['copper']})
    s.companies.update_for_organization(account_id=s.accounts[0].id, organization_id=s.org.id,
                                      company_id=s.company.id, profile=changed)
    changed_profile = enqueue(s)
    assert changed_profile.id not in {job.id, changed_snapshot.id}
    with pytest.raises(ScoringInputError):
        s.service.view(job.id, scope=s.scope)
    while run(s):
        pass
    assert s.jobs.get(changed_snapshot.id, scope=s.scope).state == 'failed'


def test_retry_upsert_after_materialization_and_no_partial_visibility(system):
    s = system
    job = enqueue(s)
    first = claim(s)
    result = s.handler(context(s, first), job.payload)
    assert count(s) == 1
    assert not s.service.view(job.id, scope=s.scope)['complete']
    assert s.service.view(job.id, scope=s.scope)['result_count'] == 0
    s.clock.now += s.jobs.settings.lease_seconds + 1
    second = claim(s)
    assert second.job.id == first.job.id and second.job.attempt_count == 2
    with pytest.raises(RetryableJobError):
        s.handler(context(s, first), job.payload)
    assert not s.jobs.complete(job.id, first.token, result)
    result2 = s.handler(context(s, second), job.payload)
    assert s.jobs.complete(job.id, second.token, result2)
    assert count(s) == 1 and s.service.view(job.id, scope=s.scope)['complete']


def test_partial_write_crash_rolls_back_and_retry_succeeds(system):
    s = system
    s.store.upsert(notice('two'), 'connector-sync-v1:ted:adapter-r1')
    job = enqueue(s)
    first = claim(s)
    ctx = context(s, first)

    class FailingConnection:
        def __init__(self, conn):
            self.conn, self.writes = conn, 0
        def execute(self, sql, params=()):
            if 'INSERT INTO scoring_results' in sql:
                self.writes += 1
                if self.writes == 2:
                    raise sqlite3.OperationalError('Synthetic private detail must never persist')
            return self.conn.execute(sql, params)

    ctx.fenced_write = lambda write: s.jobs.fenced_write(job.id, first.token,
                                                       lambda conn, now: write(FailingConnection(conn), now))
    with pytest.raises(RetryableJobError):
        s.handler(ctx, job.payload)
    assert count(s) == 0
    assert s.jobs.fail(job.id, first.token, retryable=True)
    s.clock.now += 2
    assert run(s)
    assert count(s) == 2
    assert 'Synthetic private' not in json.dumps(s.jobs.get(job.id, scope=s.scope).__dict__, default=str)


def test_expiry_during_write_rolls_back(system):
    s = system
    job = enqueue(s)
    first = claim(s)
    def delayed(conn, now):
        conn.execute('UPDATE scoring_snapshots SET candidate_count=0 WHERE identity=?', (job.payload['snapshot_id'],))
        s.clock.now += s.jobs.settings.lease_seconds + 1
    from app.jobs.models import JobValueError
    with pytest.raises(JobValueError):
        s.jobs.fenced_write(job.id, first.token, delayed)
    with closing(s.database.connect()) as conn:
        assert conn.execute('SELECT candidate_count FROM scoring_snapshots').fetchone()[0] == 1


@pytest.mark.parametrize('scope_kind', ['other_org', 'other_company', 'other_account', 'system', 'unknown'])
def test_scope_isolation(system, scope_kind):
    s = system
    job = enqueue(s)
    run(s)
    scopes = {'other_org': JobScope(s.accounts[4].id, s.other_org.id, s.other_company.id),
              'other_company': JobScope(s.accounts[0].id, s.org.id, s.second_company.id),
              'other_account': JobScope(s.accounts[1].id, s.org.id, s.company.id), 'system': JobScope(),
              'unknown': s.scope}
    with pytest.raises(ScoringAccessError):
        s.service.view('unknown' if scope_kind == 'unknown' else job.id, scope=scopes[scope_kind])


def test_revocation_and_company_switch(system):
    s = system
    job = enqueue(s)
    s.companies.set_active_for_organization(account_id=s.accounts[0].id, organization_id=s.org.id,
                                           company_id=s.second_company.id)
    assert run(s)
    assert s.service.view(job.id, scope=s.scope)['complete']
    with closing(s.database.connect()) as conn:
        conn.execute('DELETE FROM organization_members WHERE organization_id=? AND account_id=?',
                     (s.org.id, s.accounts[0].id))
        conn.commit()
    with pytest.raises(ScoringAccessError):
        s.service.view(job.id, scope=s.scope)
    with pytest.raises(ScoringAccessError):
        enqueue(s)


def test_missing_company_or_invalid_profile_permanent(system):
    s = system
    job = enqueue(s)
    with closing(s.database.connect()) as conn:
        conn.execute("UPDATE company_workspaces SET profile_json='{}' WHERE id=?", (s.company.id,))
        conn.commit()
    assert run(s)
    assert s.jobs.get(job.id, scope=s.scope).state == 'failed'
    assert s.jobs.get(job.id, scope=s.scope).attempt_count == 1
    with pytest.raises(ScoringAccessError):
        s.service.enqueue(scope=JobScope(s.accounts[0].id, s.org.id, 999999))


@pytest.mark.parametrize('payload', [{}, {'engine_version': 'evil', 'snapshot_id': 'a'*64, 'profile_digest': 'b'*64},
                                     {'source_url': 'https://example.test', 'profile': 'private'}])
def test_invalid_payload_permanent(system, payload):
    s = system
    job = s.jobs.enqueue(JOB_TYPE, payload, scope=s.scope)
    assert run(s)
    assert s.jobs.get(job.id, scope=s.scope).state == 'failed' and count(s) == 0


@pytest.mark.parametrize('changes,expected_match', [({}, True), ({'title': 'goldhofer', 'summary': None}, False),
                                                 ({'title': 'Supply of aluminium asbestos'}, False),
                                                 ({'initial_price': 10000}, False), ({'currency': 'USD'}, True),
                                                 ({'currency': None, 'initial_price': None, 'region': None}, True)])
def test_existing_prefilter_and_score_semantics(system, changes, expected_match):
    s = system
    profile = s.profile.model_copy(update={'excluded_keywords': ['asbestos']})
    n = notice(**changes)
    assert (prefilter_notice(n, profile) is not None) == expected_match
    from app.api.organization_workflow_routes import _metadata_preview_scoring
    score = score_metadata_preview(analysis_from_notice(n), profile)
    assert score == _metadata_preview_scoring(analysis_from_notice(n), profile)
    assert 0 <= score.fit_score <= 90
    assert len(score.criteria) == 6 and all(c.explanation for c in score.criteria)
    assert score_tender(analysis_from_notice(n), profile).fit_score is None or 0 <= score_tender(
        analysis_from_notice(n), profile).fit_score <= 100


def test_empty_snapshot_accurate_and_paging_ties(system):
    s = system
    empty = enqueue(s, sources=['eis'])
    assert run(s)
    view = s.service.view(empty.id, scope=s.scope)
    assert view['complete'] and view['result_count'] == 0
    assert view['source_state'] == {'eis': 'empty_or_not_synchronized'}
    s.store.upsert(notice('two'), 'connector-sync-v1:ted:adapter-r1')
    job = enqueue(s)
    assert run(s)
    first = s.service.view(job.id, scope=s.scope, limit=1)
    second = s.service.view(job.id, scope=s.scope, limit=1, offset=1)
    assert first['items'][0]['external_id'] == 'two'  # latest source snapshot first
    assert second['items'][0]['external_id'] == 'one'
    with pytest.raises(ScoringInputError):
        s.service.view(job.id, scope=s.scope, limit=101)


@pytest.mark.parametrize('sources,limit', [(['ted']*6, 20), (['unknown'], 20), (['ted'], 101), (['ted'], True),
                                          (['https://example.test'], 20), ([], 20)])
def test_selection_bounds(system, sources, limit):
    with pytest.raises(ScoringInputError):
        enqueue(system, sources=sources, limit_per_source=limit)


def test_api_auth_csrf_roles_and_isolation(system):
    s = system
    runtime = ApiRuntime(auth_service=s.auth, scoring_run_service=s.service,
                         company_service=CompanyService(s.companies), organization_service=OrganizationService(s.orgs))
    app = create_app(runtime=runtime, settings=ApiSettings(host='127.0.0.1', port=8000, reload=False, api_key='fixture'))
    path = f'/api/v1/organizations/{s.org.id}/companies/{s.company.id}/scoring/runs'
    with TestClient(app) as client:
        assert client.post(path, json={}).status_code == 401
        for account in s.accounts[:4]:
            client.cookies.set(SESSION_COOKIE, s.auth.create_session(account))
            assert client.post(path, json={}, headers={'Origin': 'https://evil.test'}).status_code == 403
            with patch('app.scoring.runs.score_metadata_preview', side_effect=AssertionError('Must not score in HTTP')):
                result = client.post(path, json={})
            assert result.status_code == 202, result.text
            job_id = result.json()['job_id']
            assert client.get(path+'/'+job_id).status_code == 200
            assert client.get(path+'/'+job_id+'?limit=101').status_code == 422
            assert client.post(path, json={'raw_profile': {}}).status_code == 422
            assert client.post(path.replace(f'companies/{s.company.id}', 'companies/0'), json={}).status_code == 422
        client.cookies.set(SESSION_COOKIE, s.auth.create_session(s.accounts[4]))
        assert client.post(path, json={}).status_code == 403
        assert client.get(path+'/'+job_id).status_code == 403


def test_migration_11_and_postgresql_sql(system):
    assert MIGRATIONS[-1].version == 11 and MIGRATIONS[-1].domain == 'scoring'
    assert MIGRATIONS[9].checksum == '95f679368a7c292f931d8b84e44ca3dec9a1c2970223f11b202337340962298b'
    assert MIGRATIONS[10].checksum == 'b4a93fcf29d7ef1a7a241e79599cb123fdcb40eed54f32e00ed46add4694547c'
    compiled = postgres_sql(MIGRATIONS[-1].sql)
    assert 'BIGINT NOT NULL REFERENCES' in compiled and 'ON DELETE CASCADE' in compiled
    system.database.migrate()
    with closing(system.database.connect()) as conn:
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()


def test_bounded_scan_does_not_score_full_source_history(system):
    s = system
    with closing(s.database.connect()) as conn:
        conn.execute('DELETE FROM source_opportunities')
        rows = []
        from dataclasses import asdict
        for i in range(1001):
            n = notice(str(i), title='Irrelevant equipment' if i else 'Supply of aluminium', summary=None)
            rows.append(('ted', str(i), json.dumps(asdict(n)), 'connector-sync-v1:ted:adapter-r1', '2026', f'{i:06d}'))
        conn.executemany('''INSERT INTO source_opportunities
            (source_id,external_id,notice_json,connector_version,first_seen,last_seen) VALUES(?,?,?,?,?,?)''', rows)
        conn.commit()
    job = enqueue(s, limit_per_source=100)
    assert run(s)
    assert s.service.view(job.id, scope=s.scope)['candidate_count'] == 0  # sole match outside bounded pool
    with closing(s.database.connect()) as conn:
        counts = json.loads(conn.execute('SELECT source_counts_json FROM scoring_snapshots').fetchone()[0])
        assert counts == {'ted': 1000}


def test_deactivated_account_and_legacy_missing_company_are_denied(system):
    s = system
    job = enqueue(s)
    with closing(s.database.connect()) as conn:
        conn.execute('UPDATE auth_accounts SET is_active=0 WHERE id=?', (s.accounts[0].id,))
        conn.commit()
    assert run(s)
    assert s.jobs.get(job.id, scope=s.scope).state == 'failed'
    with pytest.raises(ScoringAccessError):
        s.service.view(job.id, scope=s.scope)
    # Normal deletion with a retained durable job is restricted by migration 9.
    # Simulate a legacy/administratively removed parent to exercise fail-closed defense.
    with closing(s.database.connect()) as conn:
        conn.execute('PRAGMA foreign_keys=OFF')
        conn.execute('UPDATE auth_accounts SET is_active=1 WHERE id=?', (s.accounts[0].id,))
        conn.execute('DELETE FROM company_workspaces WHERE id=?', (s.company.id,))
        conn.commit()
    with pytest.raises(ScoringAccessError):
        enqueue(s)
    with pytest.raises(ScoringAccessError):
        s.service.view(job.id, scope=s.scope)


@pytest.mark.parametrize('title,summary,score', [
    ('Supply of aluminium', 'Aluminium products', 80),
    ('Equipment', 'Supply of aluminium', 70),
    ('Equipment', 'x' * 351 + ' aluminium', 35),
    ('Condition assessment', 'x' * 351 + ' aluminium', 20),
    ('Equipment', None, 0),
])
def test_preview_golden_formula(system, title, summary, score):
    result = score_metadata_preview(analysis_from_notice(notice(title=title, summary=summary)), system.profile)
    assert result.fit_score == score
    category = next(c for c in result.criteria if c.code == 'category')
    assert category.earned_points == round(30 * score / 100, 1)
    assert category.status == ('matched' if score >= 65 else 'partial' if score > 0 else 'failed')


@pytest.mark.parametrize('flags', [['--scoring'], ['--rag', '--scoring'], ['--connectors', '--scoring'],
                                 ['--rag', '--connectors', '--scoring']])
def test_cli_explicit_modes(system, flags):
    from app.rag.config import RagSettings
    with patch('app.database.config.load_database_settings', return_value=system.database.settings), \
         patch('app.rag.config.load_rag_settings', return_value=MagicMock(enabled=True)), \
         patch('app.rag.service.RagService'), \
         patch('app.rag.ingestion.RagIngestionService'), \
         patch('app.rag.ingestion.RagIngestionHandler', return_value=MagicMock()), \
         patch('app.rag.ingestion.load_ingestion_options', return_value=(MagicMock(), 10)), \
         patch('app.sources.catalog.build_source_catalog', return_value=MagicMock()), \
         patch('app.monitoring.config.load_monitoring_settings'), \
         patch('app.jobs.worker.WorkerPool') as pool, \
         patch('app.jobs.worker.threading.Event') as event, patch('signal.signal'):
        pool.return_value.stop.return_value.completed = True
        assert main(flags) == 0
        registry = pool.call_args.args[1]
        assert registry.resolve(JOB_TYPE) is not None
        if '--rag' in flags:
            assert registry.resolve('rag.ingest.v1') is not None
        if '--connectors' in flags:
            assert registry.resolve('connector.sync.v1') is not None
    assert main([]) == 2
    assert main(['--scoring', '--scoring']) == 2
