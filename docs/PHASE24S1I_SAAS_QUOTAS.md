# Phase 24S.1I SaaS quotas and fair usage

## Architecture audit

- `app/database/backend.py` owns SQLite/PostgreSQL access and controlled SQL translation. Ordered checksum migrations 1-11 already include tenant parents, jobs, connector snapshots, and scoring materialization. No Redis dependency is needed for correctness.
- `app/jobs/repository.py` is the shared durable enqueue boundary for background scoring and RAG; connectors use an intentionally system-scoped scheduler. SQLite admission already uses BEGIN IMMEDIATE. PostgreSQL queue claims and lease recovery use transaction locks and fencing.
- Queue idempotency covers job type, exact account/organization/company scope and hashed caller identity. Existing identities in queued/running/succeeded states survive retries; failure/cancellation intentionally releases identity for a new admission.
- HTTP scoring and RAG routes authenticate and check organization/company access before enqueue. The repository revalidates relational membership and company parentage, holding PostgreSQL row proofs with FOR SHARE until commit; this phase adds active-account validation. Scope is trusted internal code, never payload fields. Existing read/cancel endpoint authorization remains intact.
- Scoring snapshots and RAG document staging precede queue admission. Synchronous Discover, AI gateway/fallback, embedding/vector behavior, scoring formulas, and connector scheduling remain existing application paths. This phase changes their durable job admission boundary only.

## Implementation and policy

Migration **12**, domain `quotas`, adds `quota_admissions`: one durable row per job, a tenant key, and UTC epoch microsecond admission time. It backfills all existing account-scoped jobs using their creation time, groups organization work across accounts and companies, and keeps account-only work in its own account tenant. Old SQL migrations and checksums are unchanged. The explicit offline SQLite importer includes the ledger after jobs and rejects a version-12 source missing it. Legacy imports without a ledger backfill scoped jobs within the same destination transaction, so importing into an already migrated database also retains usage. Import counts continue to describe source rows.

Enforcement is disabled by default. Scoped jobs are still recorded while disabled, so enabling enforcement accounts for existing work. Defaults when enabled: 100 admissions per UTC calendar day, 1000 per UTC calendar month, 10 outstanding jobs. Outstanding means queued or running, including delayed jobs and expired leases awaiting recovery. All tenant durable job types share these budgets; job payloads cannot select a tenant, policy, counter, or bypass.

Configuration is operator-owned environment state:

| Setting | Default | Meaning |
| --- | --- | --- |
| `VALYQON_QUOTAS_ENABLED` | `false` | Strict true/false enforcement flag |
| `VALYQON_QUOTA_DAILY` | `100` | Daily accepted-job ceiling |
| `VALYQON_QUOTA_MONTHLY` | `1000` | Monthly accepted-job ceiling |
| `VALYQON_QUOTA_OUTSTANDING` | `10` | Outstanding-job ceiling |
| `VALYQON_QUOTA_TENANT_OVERRIDES` | `{}` | JSON tenant overrides |

Override example: `{"organization:123":{"daily":200,"monthly":2000,"outstanding":20}}`. Omitted override fields use the Limits defaults (100/1000/10), rather than inherited environment values; specify all three fields for explicit policies. Organization IDs and account IDs are positive signed-64-bit integers. Configuration rejects invalid fields, duplicate JSON keys, booleans masquerading as integers, negative limits, oversized values/JSON, and more than 1000 overrides. Zero is a hard stop; it never means unlimited. Policies are copied into immutable settings. Errors expose only a fixed configuration message. There is no public policy editing endpoint or client quota override.

Admission validates scope, then serializes the enabled tenant using a PostgreSQL transaction advisory lock derived from a stable hash of tenant identity (SQLite uses its existing writer lock). Authoritative database time is read after the lock wait. Hash collisions conservatively serialize unrelated tenants without sharing their counters. Job insertion, budget checks, and ledger insertion commit together; rejection or any storage failure rolls everything back. PostgreSQL INSERT conflicts and SQLite writer serialization preserve existing idempotency. A replay returns the existing job even at capacity without another ledger charge. A failed/cancelled identity may create a new job, which is charged again.

Accepted work consumes daily/monthly usage permanently for that window, including failed and cancelled jobs; worker attempts never charge again. There is no fragile release counter: completion, cancellation, permanent failure, and exhausted lease recovery change durable state, so outstanding capacity follows the same atomic state transition. Retryable failures and recoverable lease expiration stay outstanding. A stale worker cannot release capacity through an invalid lease. Expired work remains reserved until worker recovery marks it terminal; existing `recover_expired()` provides bounded maintenance recovery.

The trusted internal `connector.sync.v1` system scheduler remains exempt. Other unscoped jobs are rejected when enforcement is enabled. Public scoring/RAG endpoints cannot choose the connector type or a system scope. No public API quota policy trusts a caller-supplied account ID. Cross-tenant reads/cancels remain scoped by the existing application authorization checks.

Quota rejection returns HTTP 429 with a fixed message, `Cache-Control: no-store`, and `Retry-After`: time to the relevant UTC daily/monthly reset, or a one-second minimum retry interval for outstanding-only denial. This interval is advisory; completion/recovery is required to release capacity. Unauthenticated/unauthorized requests are rejected before quota information is exposed. Storage/configuration failure does not fall back to unmetered admission.

## Verification

Offline synthetic SQLite tests exercise independent connections and separate OS processes under concurrent admission, duplicate idempotent requests at capacity, durable restart behavior, transaction rollback, account/organization isolation, shared organization budgets, tenant overrides, revoked membership, inactive accounts, company parent validation, zero limits, malformed/redacted configuration, immutable policy, UTC daily/monthly/year rollover, retained period charges, terminal/retry/lease recovery, migration-11 upgrade/backfill, and offline importer preservation. HTTP tests cover authorization before quota checks and fixed 429 responses for scoring and RAG. PostgreSQL tests verify stable tenant lock arguments and SQL translation using local contracts; no PostgreSQL service is contacted.

Validation completed locally on 2026-10-08:

- `python -m pytest -q tests/test_quotas.py tests/test_jobs.py tests/test_scoring_workers.py tests/test_rag_ingestion.py tests/test_connector_workers.py tests/test_postgresql_foundation.py tests/test_organization_pdf_rag.py tests/test_ai_gateway.py tests/test_ai_cache.py tests/test_scoring.py tests/test_rag.py`: **401 passed, 1 skipped, 10 subtests passed**. One existing Starlette TestClient/httpx deprecation warning. The skip is the existing Windows symlink-privilege test; its privilege-independent symlink-policy test passed.
- After adding the separate-OS-process admission fixture, `python -m pytest -q tests/test_quotas.py`: **31 passed**, including that additional concurrency test. No application changes followed the broader passing run.
- `python -m compileall -q app tests`: passed.
- `git diff --check`: passed.
- Existing migration SQL files 1-11 have no diff; historical checksum assertions passed. Scoring golden behavior, RAG worker behavior, connector workers, AI fallback/gateway, and AI cache regression tests passed.

Earlier runs found only tests asserting migration 11 was latest. Those assertions now target migration 11 by its stable index, with a separate assertion for migration 12; historical checksum expectations were preserved.

## Operational limits

- This is durable-job admission fair usage, not token billing, provider spend accounting, synchronous request throttling, or paid-plan management. Synchronous AI/Discover/RAG ask calls remain outside these job budgets. No Phase 24S.1J dashboard or unrelated Monitoring changes are included.
- Deploy one consistent policy configuration across all enqueue processes. Settings load at repository construction; rollout/restart is required for changes. Mixed enabled/disabled writers cannot provide an enforced fleet-wide cap, because disabled writers intentionally do not enforce policy.
- PostgreSQL execution/concurrency has not been validated against a running server. SQLite concurrency and PostgreSQL lock/SQL contracts are tested offline; server validation remains a later authorized environment task.
- The ledger retains job history and uses indexed window counts plus a job-state join. Large histories may need separately designed retention/aggregation. Migration backfill runs in the existing migration transaction and may take time on a large job table.
- Existing scoring snapshot and PDF staging may occur before admission denial; quotas limit accepted jobs and outstanding worker work, not disk bytes or snapshot creation. Existing staging cleanup/retention behavior is unchanged. No storage quota is claimed.
- Outstanding slots deliberately remain reserved for stuck jobs until cancellation or lease recovery. Backfilled period usage can immediately deny new jobs after enabling a low ceiling; inspect configuration and existing workload before an operator enables enforcement.
- Existing exact-scope idempotency does not deduplicate identical work submitted by different organization members. Those are separate authorized job admissions charged to the same organization budget.

No external services, secrets, production deployment, commit, or push were used.
