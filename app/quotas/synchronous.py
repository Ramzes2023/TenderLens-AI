"""Attempt accounting, separate from durable jobs; no caller-supplied policy or IDs."""
import asyncio
import math
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from app.jobs import JobScope, JobValueError
from app.jobs.repository import JobRepository
from app.quotas import QuotaExceeded
from app.quotas.admission import lock

# Fixed server policy: request deadline plus a recovery grace period.
OPERATION_SECONDS = 300
RESERVATION_SECONDS = 360
OPERATIONS = frozenset({'analysis', 'rag', 'discovery', 'monitoring'})


class SynchronousUsage:
    def __init__(self, database, settings=None, *, clock=None):
        self.repository = JobRepository(database, quotas=settings, clock=clock)

    def initialize(self):
        self.repository.database.migrate('synchronous_usage')

    def admit(self, scope, operation):
        if operation not in OPERATIONS or not isinstance(scope, JobScope) or scope.organization_id is None:
            raise JobValueError('Organization scope required.')
        repo = self.repository
        with repo._transaction() as conn:
            repo._validate_scope(conn, scope)
            # Recheck stored roles, never accept a role assertion from HTTP input.
            roles = {'owner', 'admin', 'member'} if operation in {'analysis', 'monitoring'} else {'owner', 'admin', 'member', 'viewer'}
            row = conn.execute('SELECT role FROM organization_members WHERE organization_id=? AND account_id=?',
                               (scope.organization_id, scope.account_id)).fetchone()
            if row is None or row[0] not in roles:
                raise JobValueError('Organization access denied.')
            key = lock(conn, repo.database.backend, repo.quotas, scope, 'synchronous.' + operation)
            now = repo._now(conn)
            # Expiration never refunds accepted attempts. Recovery is tenant-local and lazy.
            conn.execute('UPDATE synchronous_usage SET finished_at=expires_at WHERE tenant_key=? AND finished_at IS NULL AND expires_at<=?', (key, now))
            if repo.quotas.enabled:
                current = datetime.fromtimestamp(now / 1000000, timezone.utc)
                day = current.replace(hour=0, minute=0, second=0, microsecond=0)
                month = day.replace(day=1)
                limits = repo.quotas.overrides.get(key, repo.quotas.limits)
                counts = [conn.execute('SELECT COUNT(*) FROM synchronous_usage WHERE tenant_key=? AND admitted_at>=?',
                                      (key, int(start.timestamp() * 1000000))).fetchone()[0] for start in (day, month)]
                active = conn.execute('SELECT COUNT(*) FROM synchronous_usage WHERE tenant_key=? AND finished_at IS NULL AND expires_at>?', (key, now)).fetchone()[0]
                if counts[0] >= limits.daily or counts[1] >= limits.monthly or active >= limits.outstanding:
                    next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
                    reset = next_month if counts[1] >= limits.monthly else day + timedelta(days=1)
                    retry = max(1, math.ceil((reset-current).total_seconds())) if counts[0] >= limits.daily or counts[1] >= limits.monthly else 1
                    raise QuotaExceeded(retry)
            identity = uuid.uuid4().hex
            conn.execute('INSERT INTO synchronous_usage(id,tenant_key,operation,admitted_at,expires_at) VALUES(?,?,?,?,?)',
                         (identity, key, operation, now, now + RESERVATION_SECONDS * 1000000))
            return identity

    def finish(self, identity):
        repo = self.repository
        with repo._transaction() as conn:
            return conn.execute('UPDATE synchronous_usage SET finished_at=? WHERE id=? AND finished_at IS NULL',
                                (repo._now(conn), identity)).rowcount == 1


@asynccontextmanager
async def admitted_operation(request, scope, operation):
    """Routes call only after authorization; short DB calls cannot be cancelled mid-insert."""
    from fastapi import HTTPException
    from app.quotas import load_quota_settings
    runtime = request.app.state.runtime
    service = getattr(runtime, 'synchronous_usage', None)
    if service is None:
        # Compatibility for injected legacy runtimes. Enabled policy always fails closed.
        if load_quota_settings().enabled:
            raise HTTPException(503, 'Usage admission unavailable.')
        yield
        return
    try:
        identity = service.admit(scope, operation)
    except QuotaExceeded as exc:
        raise HTTPException(429, 'Tenant usage quota exceeded.', headers={
            'Retry-After': str(exc.retry_after), 'Cache-Control': 'no-store'}) from None
    except JobValueError:
        raise HTTPException(403, 'Organization access denied.') from None
    except Exception:
        raise HTTPException(503, 'Usage admission unavailable.') from None
    try:
        async with asyncio.timeout(OPERATION_SECONDS):
            yield
    except TimeoutError:
        raise HTTPException(504, 'Operation timed out.', headers={'Cache-Control': 'no-store'}) from None
    finally:
        # No await: cancellation cannot strand a just-admitted reservation. A storage
        # outage leaves capacity reserved until its durable expiration.
        try:
            service.finish(identity)
        except Exception:
            from app.observability import telemetry
            telemetry.record("quota.sync_release", "unavailable")
