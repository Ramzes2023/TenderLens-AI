# Phase 24S.2B.3: synchronous AI usage and tenant quota security

Starting checkpoint: `e05631677f725f76d5e7989d33415b5396369069`.

## Architecture audit

`app/quotas/admission.py` admits durable jobs inside `JobRepository.enqueue` transactions. Its immutable ledger references durable job IDs; outstanding counts depend on queued/running states. Reusing it for HTTP calls would require artificial jobs and change existing job semantics. Job retries and idempotency already account once per accepted job and remain unchanged.

Organization PDF analysis checks stored write membership and the active company, then checks for an existing organization PDF before generation. Organization RAG checks document access; ingestion RAG checks organization/company and job scope. Company-profile PDF preview also authorizes stored write membership and company access before AI generation. Discovery resolves the authorized active company before fetching. Monitoring scans are another synchronous live-source path. These calls previously had no durable synchronous admission. Existing API security handles session identity and same-origin browser requests; it is retained. No request role assertion or API key supplies tenant identity.

AI gateway concurrency/retry and failover policy are process-local provider protections, not tenant admission. RAG retrieval/embedding and PDF indexing can also consume resources. Database conventions provide SQLite `BEGIN IMMEDIATE`, PostgreSQL transaction advisory locks, parameterized backend SQL conversion and authoritative PostgreSQL database time.

## Implementation

Additive migration 13 creates `synchronous_usage`, with UUID identities generated internally, organization keys, operation names, UTC admission timestamps, expiration and completion timestamps. Migrations 1?12 and their checksums are unchanged. SQLite-to-PostgreSQL offline import accepts and preserves the ledger; older sources may lack it. No synthetic historical synchronous usage is invented.

Admission rechecks active account, stored membership, company ownership and allowed stored role before reading quota counts. Analysis and monitoring require owner/admin/member; answering and discovery allow viewer. Routes also retain their existing authorization before admission and existing post-generation authorization checks.

One shared synchronous budget per organization covers tender PDF analysis (including parsing, AI and optional indexing), company-profile PDF generation, both RAG answering paths, discovery (including snapshot mode), and live monitoring scans. Stored duplicate PDF analyses bypass admission because they do not repeat generation/indexing. Companies within an organization share capacity.

SQLite serializes the short admission transaction with `BEGIN IMMEDIATE`; PostgreSQL uses the existing hashed tenant transaction advisory lock. Time is obtained after lock acquisition. UTC daily/monthly accepted-attempt counts and nonexpired outstanding counts are checked and the reservation inserted atomically. The connection is committed and closed before external work. Completion is a separate conditional update. No transaction spans AI generation or source fetching.

Each accepted call costs one attempt, including calls that subsequently fail, time out or are cancelled. Attempts are not refunded. A client replay gets a new identity and must pass admission again. There is no public reservation/completion API. Provider retries, cache behavior and provider failover inside that call do not create further admissions. This is resource/attempt accounting, not exact token or monetary billing.

HTTP quota rejection is a generic 429 with integer `Retry-After` and `Cache-Control: no-store`; no usage counts, tenant identifiers or limits are disclosed. Scope failures are 403 before quota counts. Missing admission under enabled policy fails closed with 503. Existing injected runtimes without the service retain compatibility only under disabled policy. Production runtime always initializes the service and fails startup safely if its schema cannot be initialized.

## Operator configuration and defaults

No new environment variables. Existing operator-owned configuration is reused unchanged:

- `VALYQON_QUOTAS_ENABLED`: strict true/false; default false.
- `VALYQON_QUOTA_DAILY`: default 100.
- `VALYQON_QUOTA_MONTHLY`: default 1000.
- `VALYQON_QUOTA_OUTSTANDING`: default 10.
- `VALYQON_QUOTA_TENANT_OVERRIDES`: existing strict JSON mapping; default `{}`. Organization overrides apply to synchronous calls.

These finite limits apply separately to the synchronous ledger and the existing durable-job ledger. They are not a single combined billing allowance. Zero limits deny all enabled admissions. Disabled production policy still records accepted synchronous attempts and lifecycle; enabling later therefore sees previously accepted attempts in the current period, consistent with durable jobs. Invalid configuration does not silently disable enforcement.

## Bounded recovery and limitations

Server-owned constants impose a 300-second coroutine deadline and a 360-second durable reservation lifetime, including a 60-second crash/cleanup grace. Completion/failure/cancellation releases outstanding capacity in `finally`. Cancellation cannot interrupt the short synchronous DB admission or completion call. Deadline returns a safe 504. Failed release emits a safe telemetry counter and leaves the durable reservation to expire.

Every admission excludes expired reservations and lazily marks that tenant's stale reservations finished. No scheduler or process-local registry is needed; process restart cannot reset counters or extend reservations. Expiration never refunds daily/monthly accepted attempts. Daily/monthly rejection waits for UTC reset; outstanding-only rejection uses a one-second retry hint, not a promise of available capacity.

Python cannot terminate an already-running thread or undo a provider request already sent. PDF/RAG thread work or a cancellation-resistant provider can continue after cancellation/timeout; stale expiry bounds reserved capacity, not execution of remote work. Use provider/source timeouts and process-level containment for stricter execution bounds. This phase does not add thread termination, verified token settlement or a unified job/synchronous budget. Cancellation, retry and failover can still incur actual provider costs within one counted attempt.

SQLite processes must share the same database file and synchronized host clock. PostgreSQL uses database time and tenant advisory locking, but a real PostgreSQL concurrency run requires an isolated integration environment; no external database was accessed. Short synchronous DB calls can briefly block the API event loop during storage contention (SQLite's existing connection timeout is ten seconds). No ledger retention cleanup is implemented; operators must plan ledger storage growth. Any future cleanup must retain current-month admissions and all live reservations.

Existing legacy account/API-key routes, Telegram and background job handlers are outside this organization HTTP admission lane. Background jobs retain their current durable quotas and idempotency. No UI scoring rules, organization data ownership, provider selection or security restrictions were changed.

## Offline validation

New deterministic tests cover same-tenant thread and separate-process concurrency, independent organizations, unauthorized scope and stored roles, quotas and safe HTTP headers, failure/cancellation/deadline release, UTC day/month rollover, restart/stale recovery, disabled/enabled policy, duplicate reuse, gateway retry/failover accounting, live discovery denial before fetching and preservation of durable-job quotas/idempotency.

Tests run with temporary storage outside the project root, pytest cache disabled, external socket connections blocked (local event-loop sockets allowed), and operator dotenv loading blocked. Only test-created synthetic configuration files under the system temporary directory are allowed by the regression harness. The seven inaccessible `.tmp-phase24s2b-*` directories are never inspected or changed. Real credentials, providers and production are not used.

Validation results (exit code 0 unless stated):

- Focused quota/job/organization/RAG/gateway/failover/PostgreSQL-fixture suite: 278 passed, 1 existing Windows symlink-privilege skip, 10 subtests passed.
- Company-profile and synchronous admission follow-up: 34 passed.
- Complete offline Python regression: 1,212 passed, 1 existing Windows symlink-privilege skip, 440 subtests passed, 254.02 seconds. Bundled Node was used for existing JS wrappers. This collection contained 14 new synchronous tests.
- Final complete synchronous suite plus observability: 24 passed, including all 15 new synchronous tests and the subsequently added release-storage-outage recovery test. No new tests were skipped.
- Standalone discovery, discovery AI-render and shortlist Node suites: 3 passed. Four existing fixture-based JS wrappers also passed separately.
- Earlier development iterations exited 1 and were corrected. The first full-run harness blocked a synthetic dotenv keyword argument and could not support Windows spawn from stdin; interrupted attempts exited 1. The corrected file-based runner completed successfully. No application change was made to bypass those tests.
- Tracked Python files plus both new modules: `compileall` passed (242 files). Historical migration checksum verification 1?12 passed. `git diff --check` passed; explicit new-file whitespace checks passed.

 Next validation step is isolated PostgreSQL multi-process concurrency and deployment-specific timeout/clock review; no commit, push, deployment or Phase 24S.2B.4 work is authorized here.
