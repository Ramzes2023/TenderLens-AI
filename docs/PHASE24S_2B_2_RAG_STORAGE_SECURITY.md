# Phase 24S.2B.2: RAG upload and storage security

Starting checkpoint: `fc916148c71e202eb01f99908dc038938e4b72d0`.
Scope: durable PDF ingestion only. No Phase 24S.2B.3, dependency changes,
migrations, external calls, deployment, commit or push.

## Audit and remediation

Previously `stage_and_enqueue` published a PDF before `JobRepository.enqueue`
ran relational quota admission. Quota denial rolled back SQL but retained the
PDF. The API correctly returned 429, masking the storage leak. Jobs are the
existing completion/retention manifest; Qdrant is not a file lifecycle authority.

The upload now validates bytes and derives the unchanged reference in memory.
A trusted internal `_prepare` callback runs in the existing enqueue transaction,
after scope validation, idempotent job selection and actual quota admission.
Only admitted or already retained jobs reach persistent staging. There is no
preliminary quota check and therefore no quota check/admission TOCTOU window.

SQLite uses the existing `BEGIN IMMEDIATE` database write lock. PostgreSQL uses
an additional organization-specific transaction advisory lock, unconditionally
including when quotas are disabled. Admission takes quota lock then storage lock;
cleanup takes only storage lock. All durable upload processes must use this
service and the same database, storage root and operator configuration. Different
organizations have independent PostgreSQL storage locks. Different PDFs in one
organization serialize, including across account and company scopes.

Lifecycle:

1. Authorize, validate bounded bytes, compute server-derived digest/reference.
2. Begin SQL transaction; validate scope and acquire relational locks.
3. Insert/select idempotent job; run actual job quota admission for a new job.
4. Enforce retained tenant document capacity; write/fsync temporary PDF and
   atomically publish it, or verify/reuse the existing PDF.
5. Commit SQL. Workers cannot see an uncommitted job; its PDF is available when
   it becomes visible.
6. On an exception after an attempted new publication, reacquire the same
   storage lock in a fresh transaction and check all retained RAG job references.
   Delete only the attempted new reference if no retained job references it.
   This also resolves a commit that succeeded but lost its acknowledgement.

Cleanup never deletes a pre-existing file. The reference check includes every
job state, not just active idempotency states: queued, running, succeeded,
failed and cancelled jobs all retain their documents. Temporary write failures
retain the existing `finally` cleanup. Existing missing files can be repaired
by duplicate uploads; failed repairs that published a referenced file preserve
that file. Integrity, path, symlink/reparse protection and 10 MiB limits remain.

## Bounded tenant storage and compatibility

`VALYQON_RAG_MAX_TENANT_DOCUMENTS` is a strict positive integer, default 1000,
maximum 1,000,000. The default bounds newly retained PDF capacity to 1000 times
10 MiB (about 9.77 GiB) per organization. This counts distinct references across
all accounts, company scopes and pipeline generations, using existing SQL job
payloads. Repeated failed-job retries sharing a reference consume one slot.
Job quotas remain unchanged and independent. Existing duplicate references are
allowed even if historical data exceeds a newly lowered limit. New references
are denied with HTTP 429 and `Cache-Control: no-store`; no time-based Retry-After
is promised for storage capacity, which needs operator retention/configuration.
Existing job quota 429/Retry-After and staging error responses are unchanged.

Document reference hashing, payload/result schemas, idempotency hashes, failed
and cancelled retry semantics, authorization, tenant isolation, worker lease
fencing, pipeline identity and Qdrant IDs/payload/filter contracts are unchanged.
No migration or historical file deletion is performed.

## Residual risks and separate work

The filesystem and SQL do not share a distributed transaction. Hard process
termination after publication but before SQL commit can leave an orphan or
`.stage-*` file. A database outage preventing reference verification causes
cleanup to fail closed and retain the file; unlink failure also requires operator
reconciliation. These failure modes are not presented as successful cleanup.
Power loss durability of filesystem directory entries remains dependent on the
filesystem and deployment. No blind directory sweep is safe.

The count cap bounds referenced files, not pre-existing or crash-created orphans,
number of tenants, job-row growth or aggregate shared-volume usage. Operators
must monitor/reserve shared-volume capacity and apply appropriate lower limits.
Retained-reference counting scans organization RAG job payloads, so SQL cost grows
with historical jobs. A separate migration should add a tenant document ledger
with unique reference, size, reservation/publication state and indexed ownership,
plus coordinated retention and crash recovery under the same locking protocol.
It would enable byte accounting, bounded indexed queries and safe attribution of
historical orphan candidates. That migration and an automatic GC are deferred.
Mixed-version writers that stage before admission must be stopped during rollout;
independent databases sharing one document directory are unsupported. The raw
store's `stage`/`delete` methods are trusted low-level operations, not admission or
retention APIs. PostgreSQL live/multi-host filesystem behavior was not exercised;
o production or external provider was contacted.

## Verification

Offline runner: `scripts/validate_phase24s2a.py`, with explicit workspace
`--basetemp` and `-p no:cacheprovider`. The runner clears inherited application
configuration, disables project dotenv loading and blocks non-loopback sockets
and DNS. Tests use fake providers and local fixtures/Qdrant only. No project
`.env`, secrets or private logs were read.

Focused command:
`python scripts/validate_phase24s2a.py tests/test_rag_ingestion.py tests/test_jobs.py tests/test_quotas.py --basetemp=.tmp-phase24s2b-focused4 -p no:cacheprovider`

Result: **146 passed, 1 skipped**, exit 0. The existing real Windows symlink test
is skipped because host privileges are unavailable; the privilege-independent
path-policy test passes. One existing Starlette deprecation warning.

Coverage includes repeated quota rejection without staging, API 429 with no
files, identical/different concurrent uploads, independent repository/store
instances with quotas disabled, tenant cap and cross-tenant isolation,
post-publication and fsync failure cleanup, SQL rollback, ambiguous successful
commit, competing admission before cleanup, all retained states, missing-file
repair, deduplication and existing
worker retry/Qdrant contracts.

Full offline regression initially completed with **1188 passed, 5 skipped,
1 failed, 440 subtests passed**. The sole failure was
`tests/test_redis_cache.py::test_env_overrides_dotenv`: the existing offline
runner blocked the synthetic `.env` fixture because workspace basetemp is below
the project root. This is a harness restriction, not a RAG regression.
A temporary guarded runner captures synthetic dotenv fixture writes and parses
only that captured text from memory, without opening any dotenv file. All
uncaptured dotenv loads return false. Full rerun:
`python .tmp-phase24s2b-offline.py --basetemp=.tmp-phase24s2b-full2 -p no:cacheprovider`
Result: **1194 passed, 5 skipped, 440 subtests passed**, exit 0, in 257.73 seconds.
One existing Starlette deprecation warning. The full rerun includes all final
new tests. The corrected dotenv fixture also passed independently.
The temporary wrapper was removed. Automatic approval review blocked recursive
deletion of the seven `.tmp-phase24s2b-*` test directories, stating only
"blocked by policy". They remain as local test artifacts: `focused`, `focused2`,
`focused3`, `focused4`, `full`, `full2`, and `harness` (each with that prefix).
`python -m compileall -q app tests scripts`: exit 0.
`git diff --check`: exit 0.

An initial test invocation hit the host's inaccessible default pytest temporary
and cache directories; explicit workspace basetemp/cache disabling resolved it.
A new running-state fixture initially violated the lease CHECK constraint and
was corrected to claim a real worker lease; no application constraint changed.

## Exact changed files

- `app/api/organization_data_routes.py`
- `app/jobs/repository.py`
- `app/rag/documents.py`
- `app/rag/ingestion.py`
- `tests/test_rag_ingestion.py`
- `docs/PHASE24S_2B_2_RAG_STORAGE_SECURITY.md`
