"""Admission runs inside the authorized job insert transaction; Redis is not involved."""
import hashlib
import math
from datetime import datetime, timezone, timedelta
from app.jobs.models import JobValueError


class QuotaExceeded(JobValueError):
    def __init__(self, retry_after):
        super().__init__('Tenant job quota exceeded.')
        self.retry_after = retry_after


def lock(conn, backend, settings, scope, job_type):
    # Trusted internal scheduler lane, never selected by a public endpoint.
    if scope.account_id is None and job_type == 'connector.sync.v1':
        return None
    if scope.organization_id is not None:
        key = 'organization:' + str(scope.organization_id)
    elif scope.account_id is not None:
        key = 'account:' + str(scope.account_id)
    else:
        if settings.enabled:
            raise JobValueError('Tenant scope required for quota admission.')
        return None
    if settings.enabled and backend == 'postgresql':
        identity = int.from_bytes(hashlib.sha256(('quota:' + key).encode()).digest()[:8], 'big', signed=True)
        conn.execute('SELECT pg_advisory_xact_lock(?)', (identity,))
    return key


def admit(conn, settings, key, job_id, now):
    if key is None:
        return
    if not settings.enabled:
        conn.execute('INSERT INTO quota_admissions(job_id,tenant_key,admitted_at) VALUES(?,?,?)', (job_id, key, now))
        return
    current = datetime.fromtimestamp(now / 1000000, timezone.utc)
    day = current.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    limits = settings.overrides.get(key, settings.limits)
    counts = [conn.execute('SELECT COUNT(*) FROM quota_admissions WHERE tenant_key=? AND admitted_at>=?',
                         (key, int(start.timestamp() * 1000000))).fetchone()[0] for start in (day, month)]
    outstanding = conn.execute("""SELECT COUNT(*) FROM quota_admissions q JOIN durable_jobs j ON j.id=q.job_id
        WHERE q.tenant_key=? AND j.state IN ('queued','running')""", (key,)).fetchone()[0]
    if counts[0] >= limits.daily or counts[1] >= limits.monthly or outstanding >= limits.outstanding:
        next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        reset = next_month if counts[1] >= limits.monthly else day + timedelta(days=1)
        retry = (max(1, math.ceil((reset-current).total_seconds()))
                 if counts[0] >= limits.daily or counts[1] >= limits.monthly else 1)
        raise QuotaExceeded(retry)
    conn.execute('INSERT INTO quota_admissions(job_id,tenant_key,admitted_at) VALUES(?,?,?)', (job_id, key, now))
