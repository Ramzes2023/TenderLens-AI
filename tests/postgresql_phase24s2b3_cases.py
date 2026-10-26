"""Real PostgreSQL cases; invoked only by the guarded standalone harness.

Not collected by ordinary pytest. Every write targets the newly created database.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import multiprocessing
from types import SimpleNamespace
import uuid
from unittest.mock import patch

from app.auth import AuthRepository
from app.jobs import JobRepository, JobScope, JobValueError
from app.jobs.config import JobSettings
from app.organizations import OrganizationRepository
from app.quotas import Limits, QuotaSettings, QuotaExceeded
from app.quotas.synchronous import SynchronousUsage, admitted_operation
from scripts.validate_phase24s2b3_postgresql import database_for_parameters, process_admission


def expect(error, action):
    try:
        action()
    except error as exc:
        return exc
    raise AssertionError("Expected rejection missing.")


def run_cases(parameters):
    db = database_for_parameters(parameters)
    try:
        db.migrate()
        db.migrate()
        from app.database.migrations import MIGRATIONS
        with closing(db.connect()) as conn:
            rows = conn.execute("SELECT version,domain,checksum FROM app_schema_migrations ORDER BY version").fetchall()
            assert [tuple(row[i] for i in range(3)) for row in rows] == [(m.version, m.domain, m.checksum) for m in MIGRATIONS]
            assert [m.version for m in MIGRATIONS] == list(range(1, 21))
            assert [m.domain for m in MIGRATIONS[-7:]] == [
                "source_observations", "legal", "deadline_alerts",
                "tender_workflows", "saved_search_filters",
                "organization_activity", "tender_team_decisions",
            ]
            assert conn.execute("SELECT COUNT(*) FROM saved_tender_team_decisions").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM saved_tender_team_decision_events").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM organization_activity_events").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM saved_search_filters").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM saved_opportunity_workflow").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM account_legal_acceptances").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM synchronous_usage").fetchone()[0] == 0
        print("PASS: migrations 1-20 including tender team decisions, checksums and replay.")

        def tenant():
            account = AuthRepository(db).create_account(uuid.uuid4().hex + "@example.test", "synthetic")
            org = OrganizationRepository(db).default_for_account(account.id)
            return JobScope(account.id, org.id)

        def service(limits=Limits(100, 100, 2)):
            # Explicit settings prevent all dotenv configuration loaders.
            return SynchronousUsage(db, QuotaSettings(True, limits))

        def execute(sql, params=()):
            with closing(db.connect()) as conn:
                with conn:
                    return conn.execute(sql, params)

        def count(scope, active=False):
            with closing(db.connect()) as conn:
                return conn.execute("SELECT COUNT(*) FROM synchronous_usage WHERE tenant_key=?" +
                                    (" AND finished_at IS NULL" if active else ""),
                                    ("organization:" + str(scope.organization_id),)).fetchone()[0]

        import threading
        for limits in (Limits(2, 100, 100), Limits(100, 2, 100), Limits(100, 100, 2)):
            scope = tenant()
            barrier = threading.Barrier(12)
            def attempt(_):
                barrier.wait(timeout=20)
                try:
                    return service(limits).admit(scope, "rag")
                except QuotaExceeded:
                    return None
            with ThreadPoolExecutor(max_workers=12) as pool:
                results = list(pool.map(attempt, range(12)))
            assert sum(item is not None for item in results) == count(scope) == 2
            assert len(set(item for item in results if item)) == 2

            process_scope = tenant()
            ctx = multiprocessing.get_context("spawn")
            gate, output = ctx.Event(), ctx.Queue()
            children = [ctx.Process(target=process_admission,
                                    args=(parameters, process_scope.values, gate, output,
                                          (limits.daily, limits.monthly, limits.outstanding))) for _ in range(8)]
            try:
                for child in children:
                    child.start()
                assert [output.get(timeout=60) for _ in children] == ["ready"] * len(children)
                gate.set()
                outcomes = [output.get(timeout=60) for _ in children]
                for child in children:
                    child.join(timeout=20)
                assert all(child.exitcode == 0 for child in children)
                assert outcomes.count("accepted") == count(process_scope) == 2
                assert outcomes.count("denied") == 6
            finally:
                for child in children:
                    if child.is_alive():
                        child.terminate()
                        child.join(timeout=10)
                output.close()
                output.join_thread()
        print("PASS: atomic thread and spawned-process admission.")

        for limits in (Limits(1, 100, 10), Limits(100, 1, 10), Limits(100, 100, 1)):
            quota_scope, usage = tenant(), service(limits)
            identity = usage.admit(quota_scope, "rag")
            denied = expect(QuotaExceeded, lambda: usage.admit(quota_scope, "analysis"))
            assert denied.retry_after >= 1 and count(quota_scope) == 1
            assert usage.finish(identity) and not usage.finish(identity)
            if limits.outstanding == 1:
                usage.admit(quota_scope, "discovery")
            else:
                expect(QuotaExceeded, lambda: usage.admit(quota_scope, "rag"))
        # Use server-derived UTC boundaries; no client-clock substitution on PostgreSQL.
        rollover, usage = tenant(), service(Limits(1, 1, 2))
        identity = usage.admit(rollover, "rag")
        usage.finish(identity)
        execute("UPDATE synchronous_usage SET admitted_at=CAST(EXTRACT(EPOCH FROM "
                "date_trunc('month',clock_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')*1000000 AS BIGINT)-1 WHERE id=?", (identity,))
        identity = usage.admit(rollover, "rag")
        usage.finish(identity)
        execute("UPDATE synchronous_usage SET admitted_at=CAST(EXTRACT(EPOCH FROM "
                "date_trunc('day',clock_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')*1000000 AS BIGINT)-1 WHERE id=?", (identity,))
        # On day 1 the previous day is also the previous month.
        with closing(db.connect()) as conn:
            day = conn.execute("SELECT EXTRACT(DAY FROM clock_timestamp() AT TIME ZONE 'UTC')").fetchone()[0]
        if day > 1:
            expect(QuotaExceeded, lambda: usage.admit(rollover, "rag"))
        else:
            usage.admit(rollover, "rag")
        print("PASS: daily, monthly, outstanding, release/no-refund and UTC windows.")

        outsider = tenant()
        usage = service()
        usage.admit(outsider, "rag")
        expect(JobValueError, lambda: usage.admit(JobScope(outsider.account_id, scope.organization_id), "rag"))
        expect(JobValueError, lambda: usage.admit(JobScope(scope.account_id, scope.organization_id, 999999999), "rag"))
        role_scope = tenant()
        for role in ("owner", "admin", "member", "viewer"):
            execute("UPDATE organization_members SET role=? WHERE account_id=? AND organization_id=?",
                    (role, role_scope.account_id, role_scope.organization_id))
            for operation in ("analysis", "monitoring", "rag", "discovery"):
                if role == "viewer" and operation in {"analysis", "monitoring"}:
                    before = count(role_scope)
                    expect(JobValueError, lambda: usage.admit(role_scope, operation))
                    assert count(role_scope) == before
                else:
                    assert usage.finish(usage.admit(role_scope, operation))
        execute("DELETE FROM organization_members WHERE account_id=? AND organization_id=?", (role_scope.account_id, role_scope.organization_id))
        expect(JobValueError, lambda: usage.admit(role_scope, "rag"))
        execute("UPDATE auth_accounts SET is_active=0 WHERE id=?", (outsider.account_id,))
        expect(JobValueError, lambda: usage.admit(outsider, "rag"))
        print("PASS: tenant isolation, membership removal, roles and inactive accounts.")

        lifecycle, usage = tenant(), service(Limits(100, 100, 1))
        stale = usage.admit(lifecycle, "rag")
        expect(QuotaExceeded, lambda: service(Limits(100, 100, 1)).admit(lifecycle, "rag"))
        execute("UPDATE synchronous_usage SET expires_at=1 WHERE id=?", (stale,))
        fresh = service(Limits(100, 100, 1)).admit(lifecycle, "analysis")
        assert not usage.finish(stale) and usage.finish(fresh)
        assert count(lifecycle) == 2  # Expiration never refunds accepted usage.
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(synchronous_usage=usage))))
        async def lifecycle_cases():
            with patch.object(usage, "finish", side_effect=RuntimeError("synthetic")):
                async with admitted_operation(request, lifecycle, "rag"):
                    pass
            expect(QuotaExceeded, lambda: usage.admit(lifecycle, "rag"))
            execute("UPDATE synchronous_usage SET expires_at=1 WHERE tenant_key=? AND finished_at IS NULL",
                    ("organization:" + str(lifecycle.organization_id),))
            entered = asyncio.Event()
            async def work():
                async with admitted_operation(request, lifecycle, "rag"):
                    entered.set()
                    await asyncio.Event().wait()
            task = asyncio.create_task(work())
            await asyncio.wait_for(entered.wait(), timeout=10)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            assert count(lifecycle, True) == 0
            from fastapi import HTTPException
            with patch("app.quotas.synchronous.OPERATION_SECONDS", 0.001):
                try:
                    async with admitted_operation(request, lifecycle, "rag"):
                        await asyncio.Event().wait()
                except HTTPException as exc:
                    assert exc.status_code == 504
                else:
                    raise AssertionError("Missing timeout.")
            assert count(lifecycle, True) == 0
            # Real gateway retry with a synthetic provider; no network calls.
            from app.llm.base import LLMNetworkError
            from app.llm.models import LLMResponse
            from app.llm.gateway import AIGateway, AIGatewaySettings, ProviderRegistry
            class Provider:
                calls = 0
                async def generate(self, prompt, *, max_tokens):
                    self.calls += 1
                    if self.calls == 1:
                        raise LLMNetworkError("synthetic")
                    return LLMResponse(text="ok", provider="gigachat", model="synthetic")
            provider, registry = Provider(), ProviderRegistry()
            registry.register("gigachat", provider)
            gateway = AIGateway(registry, AIGatewaySettings(max_attempts=2), sleeper=lambda _: asyncio.sleep(0))
            before = count(lifecycle)
            async with admitted_operation(request, lifecycle, "analysis"):
                await gateway.generate("synthetic", max_tokens=10)
            assert provider.calls == 2 and count(lifecycle) == before + 1
        asyncio.run(lifecycle_cases())
        print("PASS: cancellation, deadline, failed release, expiry/restart and synthetic retry.")

        jobs_scope = tenant()
        jobs = JobRepository(db, settings=JobSettings(), quotas=QuotaSettings(True, Limits(100, 100, 1)))
        sync = service(Limits(100, 100, 1))
        reservation = sync.admit(jobs_scope, "analysis")
        job = jobs.enqueue("fixture.work", {}, scope=jobs_scope, idempotency_key="synthetic")
        assert jobs.enqueue("fixture.work", {}, scope=jobs_scope, idempotency_key="synthetic").id == job.id
        assert jobs.get(job.id, scope=lifecycle) is None
        assert not jobs.cancel(job.id, scope=lifecycle)
        expect(QuotaExceeded, lambda: jobs.enqueue("fixture.work", {}, scope=jobs_scope))
        assert jobs.cancel(job.id, scope=jobs_scope)
        assert sync.finish(reservation)
        job = jobs.enqueue("fixture.work", {}, scope=jobs_scope)
        worker = "worker-" + uuid.uuid4().hex
        claim = jobs.claim_next(worker, job_types=["fixture.work"])
        assert claim.job.id == job.id and jobs.heartbeat(job.id, claim.token)
        assert jobs.fail(job.id, claim.token, retryable=True)
        execute("UPDATE durable_jobs SET available_at=0 WHERE id=?", (job.id,))
        retried = jobs.claim_next(worker, job_types=["fixture.work"])
        assert retried.job.attempt_count == 2
        assert not jobs.complete(job.id, claim.token, {})
        execute("UPDATE durable_jobs SET lease_expires_at=1 WHERE id=?", (job.id,))
        assert jobs.recover_expired() == 1
        assert not jobs.complete(job.id, retried.token, {})
        recovered = jobs.claim_next(worker, job_types=["fixture.work"])
        assert jobs.complete(job.id, recovered.token, {"synthetic": True})
        assert not jobs.complete(job.id, recovered.token, {})
        with closing(db.connect()) as conn:
            assert conn.execute("SELECT COUNT(*) FROM quota_admissions WHERE job_id=?", (job.id,)).fetchone()[0] == 1
        assert sync.finish(sync.admit(jobs_scope, "rag"))
        print("PASS: durable jobs, independent ledgers, idempotency, retry, recovery and fencing.")
    finally:
        db.close()
