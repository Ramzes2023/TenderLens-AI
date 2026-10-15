# Phase 24S.1C — Durable Job Queue + Worker Foundation

## Scope and starting audit

Audited branch `phase24-professional-saas-core` at
`0f153780e45f6a281aeb464c3305183ba33e2e22`; the starting worktree was clean.
No customer workflows were moved. No production services, migrations, deployments,
email, AI, or procurement calls were run. No dependencies were added or installed.

The audit covered these existing boundaries:

- `app/database/migrations.py` and `schema/*.sql`: eight ordered domains,
  auth/organizations/companies/tenders/monitoring/rag/support/operations. Identity
  is SHA-256 of `24S1A-v1:` plus SQL. Migration history is checked before applying
  additive changes; existing SQLite domain initialization can create partial
  schemas. PostgreSQL initializes dependencies in order. Historical SQL and the
  checksum algorithm remain unchanged.
- `app/database/backend.py`: runtime-owned DB-API connections; SQLite foreign keys
  enabled and a ten-second connection lock timeout. PostgreSQL uses psycopg's
  implicit transactions, a bounded pool, parameter translation, BIGINT keys and
  safe driver errors. Its connection context manager and `BEGIN IMMEDIATE` acquire
  a shared advisory transaction lock. Job transactions deliberately use explicit
  commit/rollback without that context manager so queue row locks can run concurrently.
  SQLite queue writes explicitly use `BEGIN IMMEDIATE`, never SKIP LOCKED.
- `app/database/import_sqlite.py`: read-only source snapshot, fixed parent-first
  TABLES, column/type checks, empty migrated destination and atomic transfer.
  Jobs are added last. Older sources without migration 9 may omit jobs; sources
  claiming migration 9 with a missing job table are rejected. A backed-up old
  database can first receive ordered migrations, or import its old supported
  tables into a fully migrated empty destination. No historical ledger is reset.
- `app/api/runtime.py` and `main.py`: composition root owns the database/cache;
  FastAPI lifespan closes only its owned runtime. Cache ownership/health is
  independent of queue state. No JobPool, worker threads, queue health claims,
  public job routes, or schema changes to public API models were added.
- `app/cache/config.py`, `backend.py`: optional Redis/no-op boundary with bounded
  settings, TTLs and token-owned locks. Redis remains ephemeral. None of these
  files or semantics changes. Jobs neither import nor require Redis.
- API and bot handlers use `asyncio.to_thread` for blocking storage/PDF/RAG work;
  these are request-local offloads, not durable jobs. No application-owned
  ThreadPoolExecutor or FastAPI BackgroundTasks was found. Existing implicit
  asyncio executors remain unchanged.
- `app/bot/main.py`, `monitoring.py`: the explicit asyncio task is the bot's
  `monitor_loop`, with stop event/cancellation during shutdown. It reads
  subscriptions, fetches/claims matches and sends bounded notifications, then
  waits for its configured interval. This process-local scheduler stays intact.
- `app/services/tender_analysis.py`, `app/parsers/pdf.py`, API routes and bot
  documents: PDF extraction and analysis run in the existing request flows;
  results/history are stored by existing repositories. No PDF queue integration.
- `app/rag/service.py`, embedding/store modules: PDF chunks, embeddings, Qdrant/
  SQLite vectors, retrieval and grounded answers remain in their current flow.
- `app/llm/gigachat.py`: asynchronous provider SDK call with timeout, OAuth/client
  cleanup and safe mapped errors. No provider calls or routing changes.
- `app/monitoring/service.py`, `app/sources/multi.py` and source catalog/registry:
  source fetching is asynchronous, bounded by concurrency/semaphore, and gathers
  failure-isolated reports. Existing source registry is distinct from job handlers.
- Auth verification/reset and support notification/email flows remain unchanged.
  Existing "support queue" wording denotes tickets, not an execution queue;
  "workers" also occurs in process-local rate-limit comments and Docker bot notes.
  No prior persistent execution queue or job lease table was found.
- Dockerfile and compose topology: API and bot are separate services sharing
  relational storage; bot has separate local Qdrant storage. PostgreSQL/Redis
  example overlays already exist. No worker service or automatic worker startup
  was added, and Docker was not started.
- Existing concurrency fixtures include organization invitations/companies,
  password resets, Telegram one-time linking, PostgreSQL pool initialization,
  saved opportunities/monitor claims and Redis/cache primitives. New queue tests
  use bounded barriers/events and small ThreadPoolExecutors with temporary SQLite.

## Durable storage and schema

Migration **9**, domain **jobs**, file `app/database/schema/jobs.sql`, adds only
`durable_jobs` and its indexes. Fresh/full migrations include it. Existing version
8 databases upgrade additively; migration and import tests preserve data and IDs.
Versions 1–8 retain their original checksums, tested against frozen constants.

Columns: `id`, `job_type`, `state`, `account_id`, `organization_id`, `company_id`,
`payload_json`, `result_json`, `priority`, `attempt_count`, `max_attempts`,
`available_at`, `created_at`, `started_at`, `finished_at`, `lease_expires_at`,
`lease_token_hash`, `worker_id`, `failure_code`, `idempotency_hash`.

Application UUID4 IDs contain no secrets. Tenant columns reference existing
relational parents with ON DELETE RESTRICT, keeping durable ownership attached.
Organization scope requires an account, company scope requires an organization.
Enqueue verifies the account, organization membership and company relationship.
All-null scope is explicit trusted system work, never an implicit user fallback.

PostgreSQL tenant keys/counters use the existing BIGINT dialect. Times are BIGINT
UTC epoch microseconds on both backends; PostgreSQL obtains authoritative time
from `clock_timestamp()` rather than worker machine clocks. SQLite clock injection
is available only for deterministic local tests. JSON is canonical UTF-8 TEXT:
this retains identical serialization and offline import across backends without
requiring JSONB codecs or backend-dependent result representations. The queue
never queries JSON for authorization or executable instructions.

Indexes:

- `idx_jobs_claim(priority DESC, created_at, id)` WHERE state='queued'.
- `idx_jobs_expired(lease_expires_at, id)` WHERE state='running'.
- `idx_jobs_scope(account_id, organization_id, company_id, created_at, id)`.
- `uq_jobs_idempotency(idempotency_hash)`, unique for non-null identities in queued,
  running or succeeded states. The UUID primary key also has its database index.

The relational database owns job existence, payload, scope, scheduling, attempts,
leases and outcomes. Redis cache loss cannot remove a job. No Redis wake-up
optimization is needed for this polling foundation, and Redis locks never replace
atomic database claims.

## States, scope, idempotency and serialization

Repository operations centralize the allowed transitions:

| From | To | Condition |
| --- | --- | --- |
| queued | running | Eligible atomic claim, attempts remain |
| queued | cancelled | Exact scoped cancellation |
| running | succeeded | Current unexpired lease and safe result |
| running | queued | Retryable failure with attempts remaining, or expired lease recovery |
| running | failed | Permanent/unknown/unexpected/invalid-result failure, or exhausted attempts |
| running | cancelled | Exact scoped cancellation invalidates the lease immediately |

Terminal jobs never run again. A new enqueue after failure/cancellation is a new
UUID job; successful jobs continue reserving their optional identity.

`JobService` provides enqueue/get/cancel without SQL. Lookup and cancellation
require all three scope fields to match exactly, including nulls. These are
infrastructure methods, not authorization endpoints: trusted product services
must establish current access/roles, and future handlers must reauthorize business
operations against current relational data. Stored payload fields cannot grant
access. There are no new public routes or customer-facing queued UI.

Idempotency keys are optional strings of 1–1024 characters, never stored raw.
SHA-256 covers a canonical tuple of job type, exact scope and caller identity.
A partial unique index plus `INSERT ... ON CONFLICT DO NOTHING` makes concurrent
same-identity enqueues return one queued/running/succeeded row. The first accepted
payload/policy wins; callers must change identity to request different work.
Failed/cancelled rows release the identity. If a concurrent terminal transition
releases it between a conflicting insert and lookup, enqueue returns a safe
retry-enqueue error instead of a wrong/nonexistent job. No AI fingerprints yet.

JSON accepts only exact built-in null/bool/string, signed 64-bit integer, finite
float, list and string-keyed dict values. Serialization sorts keys and uses compact
separators. It rejects arbitrary objects, bytes, tuples, non-string keys, cycles,
NaN/Infinity, invalid Unicode, nesting over 32 and more than 10,000 nodes. String
budgets are accumulated before full serialization, and final UTF-8 bytes are
bounded separately for payload/result. No pickle, eval, payload imports, command
execution or dotted function loading exists. Do not enqueue credentials, tokens,
connection URLs or other unnecessary secrets; use scoped relational references.
JSON validation does not infer whether arbitrary business text contains a secret.
Job/claim repr omits payloads/results/raw lease proof. Failure state stores only
fixed codes: handler_error, permanent_failure, unknown_type, lease_expired,
invalid_result. Exception messages/tracebacks never enter job state or worker logs.

## Claims, lease fencing and recovery

Higher numeric priority wins (-100..100). Only queued jobs with available_at <=
current time and remaining attempts are eligible. Equal priority uses created_at
then UUID as a stable tie breaker; this is FIFO where creation times differ.

SQLite: open a new connection, `BEGIN IMMEDIATE`, recover at most 100 expired
leases, select one eligible row with `ORDER BY priority DESC,created_at,id LIMIT 1`,
update to running/increment attempts/create lease, read claim, commit. Writers
serialize through SQLite's database lock, not an in-process mutex.

PostgreSQL: implicit transaction, recover at most 100 expired rows using
`FOR UPDATE SKIP LOCKED`, then:

```sql
SELECT * FROM durable_jobs
WHERE state='queued' AND available_at<=%s AND attempt_count<max_attempts
ORDER BY priority DESC,created_at,id LIMIT 1 FOR UPDATE SKIP LOCKED;
```

The locked row is updated to running, attempts incremented, start timestamp and
lease set, then committed. There is no shared advisory lock in this path. All
values are parameterized; identifier fragments come only from fixed internal
scope column names. Independent processes cannot claim the same row.

Each claim gets 32 cryptographically random bytes via token_urlsafe. Only SHA-256
of the proof is persisted; the raw token exists in the executing worker's Claim.
Heartbeat/complete/fail require an atomic database predicate of job ID, running
state, matching hash and unexpired lease. No prior Python comparison determines
ownership. PostgreSQL locks the row before refreshing time so lock waits do not
validate an expired lease against an old timestamp.

Every claim performs bounded recovery; explicit `recover_expired()` is also
available. Expired running leases become queued immediately if attempts remain;
otherwise they become failed/lease_expired. Recovery clears the old token/worker.
A later stale completion, failure or heartbeat cannot affect the replacement.
The mandatory crash test simulates A claiming/dying, expiry, B reclaiming, A trying
to finish, and B succeeding. This is **at-least-once execution**, not exactly-once
business side effects. Future handlers must be idempotent and use appropriate
business transaction/fencing contracts for external effects.

## Handlers, retries, heartbeat and cancellation

`HandlerRegistry.register('known.type', handler)` accepts explicit synchronous
callables; duplicate names, invalid names and async functions are rejected.
Registration happens in trusted application code, never in payload. Pool startup
freezes the registry. Handlers receive `(ExecutionContext, payload)` and return a
safe JSON value. Unknown types fail with unknown_type and never execute payload.

Each successful claim consumes one attempt (default 3, range 1–20), including
crashes and unknown types. `RetryableJobError` returns running to queued while
attempts remain; delay after attempt n is `min(300, 2**min(n-1,9))` seconds: 1, 2,
4, 8, ... capped at 300. Delayed retries set available_at and cannot claim early.
`PermanentJobError` fails immediately. Unexpected handler errors fail immediately;
invalid results fail with invalid_result. Exhausted retryable failures fail.
Expiry recovery retries immediately, bounded by the same attempt count.

A worker maintains an automatic heartbeat thread during each execution. The
configured interval must be <= one third of the lease duration. Lost ownership or
heartbeat storage uncertainty sets `context.lease_lost` and suppresses worker
outcome writes; subsequent DB fencing remains authoritative even before detection.
`context.should_stop` reports lease loss or shutdown. Running cancellation commits
cancelled and clears the lease immediately; the next heartbeat signals cooperative
stop. Completion races serialize: whichever terminal update wins stays terminal.

Python cannot safely terminate arbitrary running business code. Cancellation,
lease loss and shutdown are cooperative signals. A handler may continue computing
or performing external effects after losing its lease; it cannot overwrite the
new durable job outcome. Future integrations must account for this separately.

## Worker and pool lifecycle / process topology

No global executor, threads on import, or web-process worker startup exists.
`Worker.run_once()` claims one item, resolves its handler, starts automatic
heartbeat, executes, writes a fenced outcome and joins/stops heartbeat in finally.
`Worker.run()` polls with an interruptible bounded wait and stops admitting jobs
when its stop event is set. Storage exceptions leave durable recovery in charge.

`WorkerPool(repository, registry).start()` requires a nonempty registry, freezes
it, and starts exactly configured worker_count non-daemon threads once. At most
one heartbeat thread per busy worker exists: maximum 2 * worker_count threads,
without accumulating heartbeat threads between jobs. Workers share only an
admission gate; database transactions still own cross-process correctness.

`stop(timeout)` sets the stop event and waits only until the shared monotonic
deadline for in-flight workers. A claim already admitted before shutdown may
finish; subsequent admissions are rejected. In-flight handlers receive the
shutdown event and may finish gracefully. Return is `ShutdownResult(completed,
remaining_workers)`; timeout never pretends all work stopped. Repeated stops are
safe and can wait again. Stop before start is safe; stopped pools cannot restart.
The caller must keep database resources open until completed=True. After timeout,
a process supervisor must decide whether to keep waiting or terminate the process;
leases recover after a crash. Pool shutdown does not kill threads or close shared
API/cache/database resources.

Workers are a separate process/runtime concept. Web code may construct a
JobService over its database to enqueue future work, but no product wiring was
added. `python -m app.jobs.worker` exits **2** with a clear no-production-handlers
message, before loading environment or opening storage. No fake production handler
is registered. A future explicit worker composition root must register approved
handlers, own/open its database, start the pool, handle OS shutdown, await pool
completion and only then close storage. No compose worker service is enabled yet.
API health continues reporting existing infrastructure; it does not claim a
separate worker fleet is alive.

## Configuration

`load_job_settings()` loads project dotenv with override=False. Explicit
environment wins. Invalid input produces credential-free configuration errors.
The .env.example has commented canonical settings; nothing enables workers.

| Variable | Default | Bounds |
| --- | --- | --- |
| VALYQON_WORKER_COUNT | 2 | Integer 1–32 |
| VALYQON_JOB_POLL_SECONDS | 0.5 | Finite 0.01–30 |
| VALYQON_JOB_LEASE_SECONDS | 60 | Finite 0.3–3600 |
| VALYQON_JOB_HEARTBEAT_SECONDS | 10 | Finite 0.05–300 and <= lease/3 |
| VALYQON_JOB_DEFAULT_MAX_ATTEMPTS | 3 | Integer 1–20 |
| VALYQON_JOB_MAX_PAYLOAD_BYTES | 262144 | Integer 1–1048576 |
| VALYQON_JOB_MAX_RESULT_BYTES | 262144 | Integer 1–1048576 |
| VALYQON_WORKER_SHUTDOWN_SECONDS | 30 | Finite 0–300 |

Programmatic settings apply the same validation, including rejecting bools as
numeric settings. Configure heartbeat together with shorter leases. No credentials
are in JobSettings. DB/Redis configuration remains owned by prior foundations.

## Validation and remaining production prerequisites

Focused tests use VALYQON_EMAIL_MODE=disabled, temporary databases and synthetic
handlers. Coverage includes upgrade/fresh/idempotent schema, immutable historical
checksums, FK/data preservation, old/new import sources, imported job/lease values,
scoped ownership, JSON/policy bounds, concurrent identities/claims, distribution,
priority/delay/FIFO, rollback, crash/exhaustion recovery, stale writes/heartbeat,
retries, cancellation, safe registry/unknown handlers, automatic heartbeat and
lost ownership, pool count/start/stop/timeout/graceful completion, and no-handler
runner behavior. PostgreSQL tests inspect real dialect/connection adapter SQL and
transaction boundaries without an external server. Existing PostgreSQL foundation,
database and Redis/cache tests are included in focused validation. Full regression
is deliberately left for a separate clean run; Monitoring matcher remains deferred.

**POSTGRES_JOB_INTEGRATION_TESTED=NO**. No isolated real PostgreSQL server was used
or provisioned; availability was not established by connecting to any server.
SQLite concurrency and mocked PostgreSQL SQL do not prove real SKIP LOCKED behavior.
Real PostgreSQL and Redis integrations remain pending from the earlier foundations.

Before production: test migration/claim/idempotency/heartbeat/recovery/transaction
behavior against an isolated supported PostgreSQL server; perform Phase 24S.2 full
regression/security/load validation (including the known Monitoring test), confirm
backup/upgrade/import policy, and implement approved handlers and explicit worker
process wiring in the appropriate later phase. Tune DB pool/timeouts and lease
settings for expected worker count/handler durations. No production deployment or
real customer job data is part of this change.

24S.1D owns AI gateway/router; 1E owns AI cache/deduplication; 1F owns RAG scale;
1G owns connector workers/scheduling; 1H scoring separation; 1I quotas; 1J owns
fleet heartbeats/observability/logging. This foundation does not implement those.
The queue implementation is complete as infrastructure; real PostgreSQL integration
and final regression remain deployment gates, not falsely reported passing checks.

Validation record for this implementation:

- Focused run: `tests/test_jobs.py` 62 passed; PostgreSQL foundation 50 passed;
  database 9 passed; Redis/cache foundation 60 passed. **181 passed, 0 failed,
  0 skipped**, exit 0. One existing Starlette/httpx deprecation warning.
- `python -m compileall -q app tests scripts`: exit 0.
- `git diff --check`: exit 0.
- Migration 9 checksum:
  `13121241cbfd559dc535fd88407727476195c468b5698da07980e12f51196a96`.
- Full regression was not run. No commit or push was performed.

Cancellation is a scoped owner/service operation after business authorization;
there is no lease-based worker cancellation API. ExecutionContext does not expose
lease proof or a cancellation method that could revoke a replacement worker.
