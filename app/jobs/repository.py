"""Relational queue: explicit transactions and atomic lease fencing, no Redis dependency."""
import hashlib
import json
import re
import secrets
import time
import uuid
from contextlib import contextmanager

from .config import JobSettings
from .models import Claim, JobScope, JobValueError, decode_job, encode_json, job_type_name

CLAIM_SQL = """SELECT * FROM durable_jobs WHERE state='queued' AND available_at<=?
    AND attempt_count<max_attempts ORDER BY priority DESC,created_at,id LIMIT 1"""
POSTGRES_CLAIM_SQL = CLAIM_SQL + ' FOR UPDATE SKIP LOCKED'
EXPIRED_SQL = """SELECT id,attempt_count,max_attempts FROM durable_jobs
    WHERE state='running' AND lease_expires_at<=? ORDER BY lease_expires_at,id LIMIT 100"""
LEASE_CONDITION = "id=? AND state='running' AND lease_token_hash=? AND lease_expires_at>?"
FAILURE_CODES = frozenset({'handler_error', 'permanent_failure', 'unknown_type', 'lease_expired', 'invalid_result'})


def token_hash(token):
    if type(token) is not str or not 1 <= len(token) <= 128:
        raise JobValueError('Invalid lease proof.')
    return hashlib.sha256(token.encode()).hexdigest()


def retry_delay(attempt):
    return min(300, 2 ** min(attempt - 1, 9))


class JobRepository:
    def __init__(self, database, settings=None, *, clock=None):
        self.database = database
        self.settings = settings or JobSettings()
        if clock is not None and database.backend != 'sqlite':
            raise JobValueError('Clock injection is local-test only.')
        self.clock = clock or time.time

    def initialize(self):
        # Jobs reference all tenant parents; full ordered migration is intentional.
        self.database.migrate()

    @contextmanager
    def _transaction(self):
        conn = self.database.connect()
        try:
            if self.database.backend == 'sqlite':
                conn.execute('BEGIN IMMEDIATE')
            # PostgreSQL driver starts a transaction on the first statement. Do not
            # use PostgresConnection.__enter__/BEGIN: those take the global advisory lock.
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _now(self, conn):
        if self.database.backend == 'postgresql':
            return conn.execute('SELECT CAST(EXTRACT(EPOCH FROM clock_timestamp()) * 1000000 AS BIGINT)').fetchone()[0]
        return int(self.clock() * 1000000)

    def _lease_now(self, conn, job_id):
        # Refresh the authoritative time after any lock wait, rather than testing
        # an expired lease against a timestamp captured before the wait.
        if self.database.backend == 'postgresql':
            conn.execute('SELECT id FROM durable_jobs WHERE id=? FOR UPDATE', (job_id,)).fetchone()
        return self._now(conn)

    def _scope_filter(self, scope):
        if not isinstance(scope, JobScope):
            raise JobValueError('Explicit job scope required.')
        parts, params = [], []
        for name, value in zip(('account_id', 'organization_id', 'company_id'), scope.values):
            parts.append(name + (' IS NULL' if value is None else '=?'))
            if value is not None:
                params.append(value)
        return ' AND '.join(parts), params

    def _validate_scope(self, conn, scope):
        if scope.account_id is not None and not conn.execute('SELECT 1 FROM auth_accounts WHERE id=?', (scope.account_id,)).fetchone():
            raise JobValueError('Invalid stored job scope.')
        if scope.organization_id is not None and not conn.execute(
                'SELECT 1 FROM organization_members WHERE organization_id=? AND account_id=?',
                (scope.organization_id, scope.account_id)).fetchone():
            raise JobValueError('Invalid stored job scope.')
        if scope.company_id is not None and not conn.execute(
                'SELECT 1 FROM company_workspaces WHERE id=? AND organization_id=?',
                (scope.company_id, scope.organization_id)).fetchone():
            raise JobValueError('Invalid stored job scope.')

    def enqueue(self, job_type, payload, *, scope, priority=0, max_attempts=None, available_at=None, idempotency_key=None):
        job_type_name(job_type)
        self._scope_filter(scope)
        encoded = encode_json(payload, self.settings.max_payload_bytes)
        attempts = self.settings.default_max_attempts if max_attempts is None else max_attempts
        if type(priority) is not int or not -100 <= priority <= 100 or type(attempts) is not int or not 1 <= attempts <= 20:
            raise JobValueError('Invalid job policy.')
        if available_at is not None and (type(available_at) is not int or not 0 <= available_at < 2**63):
            raise JobValueError('Invalid availability timestamp.')
        fingerprint = None
        if idempotency_key is not None:
            if type(idempotency_key) is not str or not 1 <= len(idempotency_key) <= 1024:
                raise JobValueError('Invalid idempotency identity.')
            try:
                identity = json.dumps([job_type, scope.values, idempotency_key], separators=(',', ':'), ensure_ascii=True)
                fingerprint = hashlib.sha256(identity.encode()).hexdigest()
            except (ValueError, UnicodeError):
                raise JobValueError('Invalid idempotency identity.') from None
        with self._transaction() as conn:
            self._validate_scope(conn, scope)
            now = self._now(conn)
            job_id = str(uuid.uuid4())
            cursor = conn.execute('''INSERT INTO durable_jobs
                (id,job_type,state,account_id,organization_id,company_id,payload_json,priority,max_attempts,available_at,created_at,idempotency_hash)
                VALUES(?,?,'queued',?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING''',
                (job_id, job_type, *scope.values, encoded, priority, attempts, now if available_at is None else available_at, now, fingerprint))
            if cursor.rowcount == 0:
                # A conflicting row may have become terminal between INSERT and SELECT.
                # Keep enqueue atomic by locking the active identity's row in PostgreSQL.
                row = conn.execute("SELECT * FROM durable_jobs WHERE idempotency_hash=? AND state IN ('queued','running','succeeded')" +
                                   (' FOR UPDATE' if self.database.backend == 'postgresql' else ''), (fingerprint,)).fetchone()
                if row is None:
                    # The identity was released by failure/cancellation. Caller can retry
                    # explicitly rather than receiving a non-existent/incorrect job.
                    raise JobValueError('Job identity changed concurrently; retry enqueue.')
            else:
                row = conn.execute('SELECT * FROM durable_jobs WHERE id=?', (job_id,)).fetchone()
            return decode_job(row)

    def validate_scope(self, scope):
        """Revalidate stored authorization parents before worker-side processing."""
        self._scope_filter(scope)
        with self._transaction() as conn:
            self._validate_scope(conn, scope)

    def get(self, job_id, *, scope):
        clause, params = self._scope_filter(scope)
        conn = self.database.connect()
        try:
            return decode_job(conn.execute('SELECT * FROM durable_jobs WHERE id=? AND ' + clause, (job_id, *params)).fetchone())
        finally:
            conn.close()

    def cancel(self, job_id, *, scope):
        clause, params = self._scope_filter(scope)
        with self._transaction() as conn:
            now = self._now(conn)
            return conn.execute("""UPDATE durable_jobs SET state='cancelled',finished_at=?,
                lease_expires_at=NULL,lease_token_hash=NULL,worker_id=NULL
                WHERE id=? AND state IN ('queued','running') AND """ + clause, (now, job_id, *params)).rowcount == 1

    def _recover(self, conn, now):
        sql = EXPIRED_SQL + (' FOR UPDATE SKIP LOCKED' if self.database.backend == 'postgresql' else '')
        rows = conn.execute(sql, (now,)).fetchall()
        for row in rows:
            exhausted = row['attempt_count'] >= row['max_attempts']
            conn.execute('''UPDATE durable_jobs SET state=?,available_at=?,finished_at=?,failure_code='lease_expired',
                lease_expires_at=NULL,lease_token_hash=NULL,worker_id=NULL WHERE id=? AND state='running' AND lease_expires_at<=?''',
                ('failed' if exhausted else 'queued', now, now if exhausted else None, row['id'], now))
        return len(rows)

    def recover_expired(self):
        with self._transaction() as conn:
            return self._recover(conn, self._now(conn))

    def claim_next(self, worker_id):
        if type(worker_id) is not str or not re.fullmatch(r'worker-[a-f0-9]{32}', worker_id):
            raise JobValueError('Invalid worker identity.')
        with self._transaction() as conn:
            now = self._now(conn)
            self._recover(conn, now)
            row = conn.execute(POSTGRES_CLAIM_SQL if self.database.backend == 'postgresql' else CLAIM_SQL, (now,)).fetchone()
            if row is None:
                return None
            now = self._now(conn)
            token = secrets.token_urlsafe(32)
            conn.execute("""UPDATE durable_jobs SET state='running',attempt_count=attempt_count+1,
                started_at=?,finished_at=NULL,lease_expires_at=?,lease_token_hash=?,worker_id=? WHERE id=? AND state='queued'""",
                (now, now + int(self.settings.lease_seconds * 1000000), token_hash(token), worker_id, row['id']))
            return Claim(decode_job(conn.execute('SELECT * FROM durable_jobs WHERE id=?', (row['id'],)).fetchone()), token)

    def heartbeat(self, job_id, token):
        with self._transaction() as conn:
            now = self._lease_now(conn, job_id)
            return conn.execute('UPDATE durable_jobs SET lease_expires_at=? WHERE ' + LEASE_CONDITION,
                (now + int(self.settings.lease_seconds * 1000000), job_id, token_hash(token), now)).rowcount == 1

    def complete(self, job_id, token, result):
        encoded = encode_json(result, self.settings.max_result_bytes)
        with self._transaction() as conn:
            now = self._lease_now(conn, job_id)
            return conn.execute("""UPDATE durable_jobs SET state='succeeded',result_json=?,finished_at=?,failure_code=NULL,
                lease_expires_at=NULL,lease_token_hash=NULL,worker_id=NULL WHERE """ + LEASE_CONDITION,
                (encoded, now, job_id, token_hash(token), now)).rowcount == 1

    def fail(self, job_id, token, *, retryable=False, code='handler_error'):
        if type(code) is not str or code not in FAILURE_CODES or type(retryable) is not bool:
            raise JobValueError('Invalid safe failure policy.')
        with self._transaction() as conn:
            now = self._lease_now(conn, job_id)
            row = conn.execute('SELECT attempt_count,max_attempts FROM durable_jobs WHERE ' + LEASE_CONDITION +
                               (' FOR UPDATE' if self.database.backend == 'postgresql' else ''),
                               (job_id, token_hash(token), now)).fetchone()
            if row is None:
                return False
            retry = retryable and row['attempt_count'] < row['max_attempts']
            return conn.execute('''UPDATE durable_jobs SET state=?,failure_code=?,available_at=?,finished_at=?,
                lease_expires_at=NULL,lease_token_hash=NULL,worker_id=NULL WHERE ''' + LEASE_CONDITION,
                ('queued' if retry else 'failed', code, now + retry_delay(row['attempt_count']) * 1000000 if retry else now,
                 None if retry else now, job_id, token_hash(token), now)).rowcount == 1
