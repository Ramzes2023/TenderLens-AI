"""Offline synchronous attempt admission and lifecycle tests."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from app.auth import AuthRepository
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import JobRepository, JobScope, JobValueError
from app.organizations import OrganizationRepository
from app.quotas import Limits, QuotaSettings, QuotaExceeded
from app.quotas.synchronous import SynchronousUsage, admitted_operation, RESERVATION_SECONDS


@pytest.fixture
def usage(tmp_path):
    db = Database(DatabaseSettings('', tmp_path / 'usage.db'))
    db.migrate()
    account = AuthRepository(db).create_account('usage@example.test', 'synthetic')
    org = OrganizationRepository(db).default_for_account(account.id)
    now = [datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp()]
    service = SynchronousUsage(db, QuotaSettings(True, Limits(5, 8, 2)), clock=lambda: now[0])
    yield service, JobScope(account.id, org.id), now
    db.close()


def count(service):
    with closing(service.repository.database.connect()) as conn:
        return conn.execute('SELECT COUNT(*) FROM synchronous_usage').fetchone()[0]


def test_concurrent_same_tenant_and_restart(usage):
    service, scope, now = usage
    def submit(_):
        other = SynchronousUsage(service.repository.database, service.repository.quotas, clock=lambda: now[0])
        try:
            return other.admit(scope, 'rag')
        except QuotaExceeded:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(submit, range(16)))
    assert sum(x is not None for x in results) == 2
    assert count(service) == 2
    with pytest.raises(QuotaExceeded):
        submit_again = service.admit(scope, 'analysis')
    now[0] += RESERVATION_SECONDS
    restarted = SynchronousUsage(service.repository.database, service.repository.quotas, clock=lambda: now[0])
    restarted.admit(scope, 'rag')
    assert not restarted.finish(next(x for x in results if x))
    assert count(service) == 3


def test_independent_organizations_and_unauthorized(usage):
    service, scope, _ = usage
    account = AuthRepository(service.repository.database).create_account('other@example.test', 'synthetic')
    org = OrganizationRepository(service.repository.database).default_for_account(account.id)
    other = JobScope(account.id, org.id)
    for _ in range(2):
        service.admit(scope, 'rag')
        service.admit(other, 'discovery')
    with pytest.raises(JobValueError):
        service.admit(JobScope(account.id, scope.organization_id), 'rag')
    with pytest.raises(JobValueError):
        service.admit(JobScope(scope.account_id, scope.organization_id, 999999), 'rag')
    assert count(service) == 4


def test_exhaustion_rollover_and_no_refund_or_replay(usage):
    service, scope, now = usage
    service.repository.quotas = QuotaSettings(True, Limits(1, 1, 1))
    identity = service.admit(scope, 'rag')
    assert service.finish(identity)
    assert not service.finish(identity)
    with pytest.raises(QuotaExceeded) as rejected:
        service.admit(scope, 'discovery')
    assert rejected.value.retry_after == 1
    now[0] += 2
    service.admit(scope, 'analysis')
    assert count(service) == 2


def test_daily_rollover_does_not_reset_month(usage):
    service, scope, now = usage
    now[0] = datetime(2026, 10, 8, 23, 59, 59, tzinfo=timezone.utc).timestamp()
    service.repository.quotas = QuotaSettings(True, Limits(1, 1, 1))
    service.finish(service.admit(scope, 'rag'))
    now[0] += 2
    with pytest.raises(QuotaExceeded) as rejected:
        service.admit(scope, 'rag')
    assert rejected.value.retry_after > 86400


def test_disabled_policy_and_background_jobs_unchanged(usage):
    service, scope, now = usage
    service.repository.quotas = QuotaSettings(False, Limits(0, 0, 0))
    for _ in range(4):
        service.admit(scope, 'rag')
    jobs = JobRepository(service.repository.database, quotas=QuotaSettings(True, Limits(1, 1, 1)), clock=lambda: now[0])
    job = jobs.enqueue('fixture.work', {}, scope=scope, idempotency_key='same')
    assert jobs.enqueue('fixture.work', {}, scope=scope, idempotency_key='same').id == job.id
    assert jobs.cancel(job.id, scope=scope)
    with pytest.raises(QuotaExceeded):
        jobs.enqueue('fixture.work', {}, scope=scope)
    service.admit(scope, 'analysis')


def test_failure_cancellation_and_safe_http_rejection(usage):
    service, scope, _ = usage
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(synchronous_usage=service))))
    async def scenario():
        with pytest.raises(RuntimeError):
            async with admitted_operation(request, scope, 'rag'):
                raise RuntimeError('synthetic')
        entered = asyncio.Event()
        async def work():
            async with admitted_operation(request, scope, 'rag'):
                entered.set()
                await asyncio.Event().wait()
        task = asyncio.create_task(work())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        service.repository.quotas = QuotaSettings(True, Limits(2, 8, 2))
        with pytest.raises(HTTPException) as rejected:
            async with admitted_operation(request, scope, 'rag'):
                pytest.fail('rejected operation ran')
        assert rejected.value.status_code == 429
        assert rejected.value.headers['Cache-Control'] == 'no-store'
        assert int(rejected.value.headers['Retry-After']) >= 1
    asyncio.run(scenario())
    with closing(service.repository.database.connect()) as conn:
        assert conn.execute('SELECT COUNT(*) FROM synchronous_usage WHERE finished_at IS NULL').fetchone()[0] == 0
    assert count(service) == 2


def test_retry_and_failover_one_admitted_operation(usage):
    from app.llm.base import LLMNetworkError
    from app.llm.models import LLMResponse
    from app.llm.gateway import AIGateway, ProviderRegistry
    from app.llm.gateway import AIGatewaySettings
    service, scope, _ = usage
    class Provider:
        calls = 0
        async def generate(self, prompt, *, max_tokens):
            self.calls += 1
            if self.calls == 1:
                raise LLMNetworkError('synthetic')
            return LLMResponse(text='ok', provider='gigachat', model='synthetic')
    provider = Provider()
    registry = ProviderRegistry()
    registry.register('gigachat', provider)
    gateway = AIGateway(registry, AIGatewaySettings(max_attempts=2), sleeper=lambda _: asyncio.sleep(0))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(synchronous_usage=service))))
    async def run():
        async with admitted_operation(request, scope, 'analysis'):
            await gateway.generate('synthetic', max_tokens=10)
    asyncio.run(run())
    assert provider.calls == 2
    assert count(service) == 1
    from app.llm.failover import FailoverGateway
    class Unavailable:
        async def generate(self, prompt, *, max_tokens):
            raise LLMNetworkError('synthetic')
    primary_registry = ProviderRegistry()
    primary_registry.register('gigachat', Unavailable())
    backup_registry = ProviderRegistry()
    backup_registry.register('groq', provider)
    failover = FailoverGateway(
        AIGateway(primary_registry, AIGatewaySettings(max_attempts=1)),
        AIGateway(backup_registry, AIGatewaySettings(provider='groq', max_attempts=1)))
    async def fallback():
        async with admitted_operation(request, scope, 'analysis'):
            await failover.generate('synthetic', max_tokens=10)
    asyncio.run(fallback())
    assert provider.calls == 3
    assert count(service) == 2


@pytest.fixture
def api_usage():
    from tests.test_organization_pdf_rag import OrganizationPdfRagTests
    helper = OrganizationPdfRagTests()
    helper.setUp()
    service = SynchronousUsage(helper.tenders.database, QuotaSettings(True, Limits(1, 1, 1)))
    service.initialize()
    helper.client.app.state.runtime.synchronous_usage = service
    try:
        yield helper, service
    finally:
        helper.doCleanups()


def test_authorized_rag_429_and_unauthorized_no_disclosure(api_usage):
    helper, service = api_usage
    digest = 'a' * 64
    helper.save_record(helper.owner, helper.organization.id, digest)
    helper.as_account(helper.owner)
    payload = {'pdf_sha256': digest, 'question': 'synthetic'}
    assert helper.client.post(helper.base('/rag/ask'), json=payload).status_code == 200
    rejected = helper.client.post(helper.base('/rag/ask'), json=payload)
    assert rejected.status_code == 429
    assert rejected.headers['cache-control'] == 'no-store'
    assert int(rejected.headers['retry-after']) >= 1
    helper.as_account(helper.outsider)
    denied = helper.client.post(helper.base('/rag/ask'), json=payload)
    assert denied.status_code == 403
    assert 'retry-after' not in denied.headers
    assert count(service) == 1
    assert len(helper.rag.answer_calls) == 1


def test_analysis_duplicate_reuses_result_without_admission(api_usage):
    from unittest.mock import AsyncMock, patch
    helper, service = api_usage
    helper.as_account(helper.member)
    files = {'file': ('synthetic.pdf', b'%PDF-synthetic', 'application/pdf')}
    with patch('app.api.organization_data_routes.summarize_pdf', AsyncMock(return_value=helper.summary())), patch('app.api.organization_data_routes.analyze_tender', AsyncMock(return_value=helper.result())) as generate:
        assert helper.client.post(helper.base('/analysis/pdf'), files=files).status_code == 200
        duplicate = helper.client.post(helper.base('/analysis/pdf'), files=files)
        assert duplicate.status_code == 200
        assert duplicate.json()['duplicate']
        assert generate.await_count == 1
    assert count(service) == 1


def test_live_discovery_is_admitted_before_fetch():
    from tests.test_organization_workflows import OrganizationWorkflowTests
    helper = OrganizationWorkflowTests()
    helper.setUp()
    try:
        database = Database(DatabaseSettings('', helper.path))
        service = SynchronousUsage(database, QuotaSettings(True, Limits(0, 0, 0)))
        service.initialize()
        helper.client.app.state.runtime.synchronous_usage = service
        helper.as_account(helper.owner)
        helper.create_company('Synthetic discovery')
        rejected = helper.client.post(f'/api/v1/organizations/{helper.organization.id}/discover/tenders')
        assert rejected.status_code == 429, rejected.text
        assert rejected.headers['cache-control'] == 'no-store'
        assert count(service) == 0
    finally:
        helper.doCleanups()


def _process_admit(arguments):
    path, account_id, organization_id, now = arguments
    database = Database(DatabaseSettings('', __import__('pathlib').Path(path)))
    service = SynchronousUsage(database, QuotaSettings(True, Limits(5, 8, 2)), clock=lambda: now)
    try:
        try:
            return service.admit(JobScope(account_id, organization_id), 'rag')
        except QuotaExceeded:
            return None
    finally:
        database.close()


def test_atomic_across_application_processes(usage):
    import subprocess
    import sys
    service, scope, now = usage
    arguments = (str(service.repository.database.settings.path), scope.account_id, scope.organization_id, now[0])
    script = 'from tests.test_synchronous_usage import _process_admit; print(_process_admit(' + repr(arguments) + '))'
    def submit(_):
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        return None if result.stdout.strip() == 'None' else result.stdout.strip()
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(submit, range(8)))
    assert sum(x is not None for x in results) == 2
    assert count(service) == 2


def test_deadline_releases_capacity(usage, monkeypatch):
    service, scope, _ = usage
    monkeypatch.setattr('app.quotas.synchronous.OPERATION_SECONDS', 0.001)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(synchronous_usage=service))))
    async def scenario():
        with pytest.raises(HTTPException) as timed_out:
            async with admitted_operation(request, scope, 'rag'):
                await asyncio.Event().wait()
        assert timed_out.value.status_code == 504
    asyncio.run(scenario())
    identity = service.admit(scope, 'rag')
    assert service.finish(identity)


def test_stored_viewer_cannot_admit_analysis(usage):
    service, scope, _ = usage
    with closing(service.repository.database.connect()) as conn:
        conn.execute("UPDATE organization_members SET role='viewer' WHERE organization_id=? AND account_id=?", (scope.organization_id, scope.account_id))
        conn.commit()
    with pytest.raises(JobValueError):
        service.admit(scope, 'analysis')
    assert count(service) == 0
    service.admit(scope, 'rag')


def test_company_profile_generation_admission_and_authorization(api_usage):
    from unittest.mock import AsyncMock, patch
    helper, service = api_usage
    helper.as_account(helper.owner)
    company = helper.companies.active_for_organization(helper.owner.id, helper.organization.id)
    service.repository.quotas = QuotaSettings(True, Limits(0, 0, 0))
    endpoint = helper.base(f'/companies/{company.id}/profile-from-pdf/preview')
    files = {'file': ('synthetic.pdf', b'%PDF-synthetic', 'application/pdf')}
    with patch('app.api.organization_company_routes.summarize_pdf', AsyncMock()) as parse, patch('app.api.organization_company_routes.analyze_company_search_profile', AsyncMock()) as generate:
        rejected = helper.client.post(endpoint, files=files)
        assert rejected.status_code == 429
        assert rejected.headers['cache-control'] == 'no-store'
        helper.as_account(helper.outsider)
        assert helper.client.post(endpoint, files=files).status_code == 403
        parse.assert_not_awaited()
        generate.assert_not_awaited()
    assert count(service) == 0


def test_failed_release_retains_capacity_until_expiration(usage):
    from unittest.mock import patch
    from app.observability import Telemetry
    service, scope, now = usage
    service.repository.quotas = QuotaSettings(True, Limits(5, 8, 1))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(synchronous_usage=service))))
    metrics = Telemetry(metrics=True)
    async def work():
        with patch.object(service, 'finish', side_effect=RuntimeError('synthetic storage failure')), patch('app.observability.telemetry', metrics):
            async with admitted_operation(request, scope, 'rag'):
                pass
    asyncio.run(work())
    with pytest.raises(QuotaExceeded):
        service.admit(scope, 'rag')
    assert metrics.snapshot()[0]['operation'] == 'quota.sync_release'
    assert metrics.snapshot()[0]['outcome'] == 'unavailable'
    now[0] += RESERVATION_SECONDS
    service.admit(scope, 'rag')
    assert count(service) == 2
