# Phase 24S.1A — PostgreSQL foundation for VALYQON AI

This phase implements the PostgreSQL persistence path and offline operational tooling.
It does not migrate existing production data, deploy infrastructure, or begin Phase 24T.
The starting branch was `phase24-professional-saas-core`, clean at `a7bd048`.

## Persistence audit

Previously, seven implementations opened short-lived `sqlite3` connections directly.
All relational stores used the established `DATABASE_URL` setting, normally
`sqlite:///./data/tenderlens.db`. Constructors accepted a SQLite `Path`. Schema creation
was distributed across repository initializers; support messages were created lazily.
`schema_meta.schema_version=1` covered tender storage rather than the entire application.
Organization helpers performed additive schema changes and account/company backfills.

| Domain audited | Implementation and existing persistence |
| --- | --- |
| Accounts, registration, authentication | `app/auth/repository.py`, `service.py`, `passwords.py`; `auth_accounts`, normalized emails, password hashes, owner namespaces |
| Sessions | Auth repository/service; `auth_sessions`, hashed tickets, expiry, revocation, last-seen timestamps |
| Email verification | Auth repository/service and email delivery/routes; `auth_email_verifications`, one-time claims, cooldown, grandfathered legacy accounts |
| Password reset | Auth repository/service; `auth_password_resets`, rotation, conditional consumption, password update and all-session revocation |
| Telegram linking | Auth repository/service and bot handlers; `auth_telegram_links`, conditional claims and guarded owner migration |
| Companies | `app/companies/repository.py`, service; `company_workspaces`, `company_active`, profiles serialized as JSON text, personal/shared ownership |
| Organizations, roles, invitations | `app/organizations/repository.py`, `migration.py`, service; `organizations`, `organization_members`, `organization_invitations`, personal workspace backfill, last-owner restrictions |
| Monitoring and automation | `app/monitoring/repository.py`, service and bot monitoring loop; `monitor_subscriptions`, `monitor_seen`, unique dedup claims; no separate automation database |
| Saved opportunities / shortlist | `app/database/repository.py`; `saved_opportunities`, unique organization/company/source/external-ID scope |
| Search history | Tender repository and organization workflow routes; `discovery_search_history`, JSON snapshots and source outcomes |
| Tender/PDF analysis | Tender repository, analysis and PDF handlers; `tenders`, analysis/scoring JSON, PDF digest and metadata; no raw PDF bytes in this database |
| PDF/RAG vectors and metadata | `app/rag/store.py`: legacy `rag_chunks`, float32 binary vectors and chunk metadata. Active `RagService` uses `app/rag/qdrant_store.py` and local Qdrant, independently persisted |
| Notifications | Monitoring subscriptions and dedup state above; notifications inbox has no implementation/database |
| Support | `app/support.py`, support routes; `support_tickets`, `support_ticket_messages`, owner-scoped tickets and support-authorized mutations |
| Billing foundation | UI/support category only; billing/payments/subscriptions have no database tables or write service in this revision |
| Other storage/configuration | Company fallback profile is read from a JSON configuration file. Source credentials and LLM configuration are environment configuration, not relational repositories. Rate limiting is existing in-process state |

The audit also covered configuration/dotenv loaders, temporary-SQLite tests, dependency
manifests, FastAPI and bot composition roots, Dockerfile, both Compose files, deployment
health checks, CI, README, architecture/security and deployment documentation.
No real `.env` secrets, customer database contents, or backup contents were inspected.

The installed `qdrant-client` implementation was also inspected: its local collection
persistence owns a separate `storage.sqlite` per collection beneath `RAG_QDRANT_PATH`
(API and bot use different directories). Those vendor-managed SQLite files and Qdrant's
local file locking remain unchanged. They are not repositories sharing `DATABASE_URL`
and must be backed up with the complete Qdrant directories. Moving active RAG to a
server-backed vector store belongs to Phase 24S.1F.

## Database boundary and SQL decisions

`app/database/backend.py` supplies a runtime-owned `Database`, connection leases,
safe errors, controlled identifier quoting, catalog helpers and PostgreSQL SQL compilation.
All seven repositories use this boundary. Services, authorization filters and API response
shapes remain in place. This avoids an ORM/business-logic rewrite.

SQLite still uses normal isolated file connections with foreign keys enabled. PostgreSQL
uses psycopg 3 and its official pool. A repository method acquires one lease for its whole
operation, rather than acquiring a connection per SQL statement. API/bot repositories
share their process's `Database`. There is no global pool registry or shared raw connection.
Standalone consumers may pass a `Database`, `DatabaseSettings`, SQLite path, or URL;
they must close the `Database` they own. Repository `.path` is a SQLite path or `None`.

PostgreSQL changes are explicit and bounded:

- `?` placeholders compile to psycopg `%s`; values stay separate from SQL. Quoted literals
  and identifiers are preserved. The compiler supports the project's fixed SQL subset,
  not arbitrary SQL, procedural bodies or SQL supplied by customers.
- Durable IDs use `BIGINT GENERATED BY DEFAULT AS IDENTITY`, permitting explicit import IDs.
  Other integer columns use `BIGINT`, including synthetic web/organization owner IDs.
- Inserted-ID access uses native `RETURNING id`, exposed to existing repository code
  through the cursor boundary. Native `ON CONFLICT` handles upserts and deduplication;
  customer-facing repositories no longer issue `INSERT OR IGNORE`.
- Binary legacy vectors use `BYTEA`. JSON remains serialized `TEXT`.
- ISO timestamp strings remain `TEXT` deliberately: existing response contracts,
  lexicographic expiry comparisons, precision and historical strings are preserved
  byte-for-byte. This phase does not normalize historical timestamps to `TIMESTAMPTZ`.
- Boolean contracts remain checked numeric flags (`CHECK ... IN (0,1)`), avoiding implicit
  integer/boolean casts throughout existing SQL. Native BOOLEAN is a possible later
  versioned migration, not an unreviewed storage/API change here.
- PostgreSQL does not use SQLite `NOCASE`. Explicit `lower(email)` comparisons and unique
  expression indexes enforce case-insensitive account and pending-invitation uniqueness.
  Services retain existing Python email normalization. Company-name equality stays exact.
- SQLite `PRAGMA`/`sqlite_master` stay inside backend-specific catalog/source inspection.
  PostgreSQL catalogs use `information_schema` in the connection's current schema.
- Existing foreign keys, uniqueness, partial indexes, NULL semantics and checks are
  retained. No new cascades delete historical shortlist/search/support records.

## Configuration and dependencies

`DATABASE_URL` remains the single canonical setting; no competing URL variable was added.
Dotenv loading does not override explicit environment values. The URL is excluded from
settings representations. Invalid URLs/pool settings produce credential-free diagnostics.

```dotenv
# Local development (project-relative path)
DATABASE_URL=sqlite:///./data/tenderlens.db
VALYQON_DATABASE_REQUIRE_POSTGRES=false

# Future PostgreSQL configuration — illustrative placeholders only
# DATABASE_URL=postgresql://APP_USER:PASSWORD_PLACEHOLDER@DB_HOST/DB_NAME?sslmode=verify-full
# VALYQON_DATABASE_REQUIRE_POSTGRES=true
VALYQON_DB_POOL_MIN=1
VALYQON_DB_POOL_MAX=10
VALYQON_DB_POOL_TIMEOUT=10
VALYQON_EMAIL_MODE=disabled
```

Inject the real PostgreSQL URL through the operator's secret configuration, not shell
history, command arguments, logs, source control or shared diagnostic bundles. Percent-encode
URL components correctly. Pool limits are per process: budget API replicas, bot processes,
operator tools and PostgreSQL reserved connections together. Bounds are 0..100 for minimum,
1..100 for maximum, minimum <= maximum, and acquisition/startup timeout >0 and <=120 seconds.

Supported schemes are `postgresql://`, `postgres://`, `sqlite:///`; a plain filesystem path
is also supported locally. File-backed SQLite is the supported test mode. The previous
project-relative `/./` and absolute Windows/POSIX URL conventions are preserved.

Future PostgreSQL production deployments **must** set
`VALYQON_DATABASE_REQUIRE_POSTGRES=true`. This rejects missing/default SQLite selection.
Every PostgreSQL connection/configuration failure fails closed, never falls back to SQLite.
The current Phase 24R production Compose files remain unchanged and still select SQLite;
`APP_ENV=production` alone does not trigger a cutover in this phase.

Added production declarations in `requirements.txt`:

```text
psycopg[binary]>=3.2,<4
psycopg-pool>=3.2,<4
```

They were not installed/downloaded during this work. Lazy imports keep SQLite tests usable
without them. Operators must provision them in the project's isolated environment/image
and verify the chosen PostgreSQL server/version before cutover. No system service is installed
or started by this code. PostgreSQL 14+ is the intended deployment baseline, pending integration.

## Pool lifecycle, transactions and health

Pool initialization is thread-safe, bounded and explicit (`open=False`, then wait for ready).
Psycopg connection startup gets a bounded connection timeout. Acquisition uses the configured
timeout. Commit/rollback errors are redacted; close rolls back unfinished read/write transactions
before release. If rollback fails, the connection is closed before the official pool receives it.
Pool retry diagnostics receive generic connection exceptions and safe connection representations.

FastAPI lifespan owns runtime cleanup in `finally`; bot shutdown and CLI tools close their owned
database. Leases keep the original pool reference so outstanding leases can be returned after
shutdown begins. Tests use runtime-owned fakes and temporary files, never hidden global pools.

PostgreSQL write transactions take transaction-scoped advisory lock `240001` **before**
authorization/read-before-write logic. All application writers, migration runners and importer
share it. Reads remain concurrent. This deliberately conservative database-wide write
serialization preserves SQLite's security invariants across multiple API/bot processes:
last-owner checks, invitations/roles, company active selection, auth rotation/cooldowns,
owner linking and support mutations cannot race another cooperating application writer.
Unique constraints and conditional token updates add independent safeguards.

The lock is released automatically on commit/rollback. It is cooperative: manual SQL tools must
remain offline during import/cutover, and external writers must follow the same protocol.
Do not change PostgreSQL's default READ COMMITTED isolation without auditing snapshot/lock
semantics. Finer-grained locking and throughput measurements belong to a later reviewed phase.
This implementation makes no high-throughput or load-test claim.

Atomic operations audited: registration + owner ID + personal org/member; role/last-owner
mutations; invitation validation + membership + acceptance; token rotation/cooldown;
password reset claim + password change + session revocation; email verification claim + account
update; company mutations + active selection; shortlist/search authorization + writes;
monitoring unique claims; support ticket ID/public-ID and message/status writes; legacy vector
replacement. No billing writes exist. Tenant filters, sessions, rate limiting, CSRF/origin
checks and parameterized values are retained. The Monitoring matcher was not modified.

`/health` preserves the VALYQON AI response shape. Runtime database readiness runs a usable
`SELECT 1` through the chosen backend, returning only `ready`/`unavailable`. It does not expose
DSNs, hosts, usernames, passwords or raw driver exceptions.

## Schema migrations and fresh setup

`app/database/migrations.py` orders eight immutable migrations: auth, organizations,
companies, tenders, monitoring, legacy RAG, support, operational import metadata.
`app_schema_migrations` records version/domain/checksum. `schema_meta.schema_version=1`
remains for legacy compatibility; it is not overwritten to disguise unsupported schemas.
Unknown versions/changed checksums stop migration. Fresh and existing databases use additive
DDL/backfills, never DROP/recreate. Freeze released SQL assets and upgrade helpers; append
new numbered migrations for future changes rather than editing applied migrations.

Each migration invocation runs in one transaction. SQLite statements are executed individually
because `sqlite3.executescript` would commit outside the caller's transaction. PostgreSQL DDL
and ledger writes share the write lock/transaction. Failures roll back and stop. Repeated
startup verifies versions and safely repeats legacy personal-org/company backfill where needed.
Standalone SQLite repositories retain domain-limited initialization for existing fixtures;
the explicit CLI and PostgreSQL path initialize all domains in dependency order.

Before any schema upgrade, take and verify a backup. For a **new isolated** PostgreSQL database,
an operator creates the database/role, grants required schema privileges, selects an application
schema via secure connection configuration, provisions dependencies, then runs:

```text
python -m app.database.migrations
```

The command reads `DATABASE_URL` and reports only a safe success/failure. PostgreSQL API/bot
startup also applies pending additive migrations and stops if they fail. Data import is never
part of startup. Migration privileges are currently required by startup/backfill; separating
DDL and steady-state runtime roles is a future operational hardening option.

For local/test SQLite, keep the default URL or set an explicit temporary path and run the same
command. Do not point development tests at customer data.

## SQLite -> PostgreSQL import procedure

1. Schedule an operator-reviewed cutover window in Phase 24T. Stop **all** writers (API, bot,
   scripts). Disable email and avoid live AI/procurement calls in rehearsal. Back up SQLite
   using SQLite's backup API or a coordinated stopped-process snapshot, including any WAL
   state. Do not copy a live `.db` file without its committed WAL data. Back up Qdrant and
   relevant configuration independently; this tool does not import Qdrant.
2. Retain the original backup unchanged. If needed, upgrade a **separate backed-up working
   copy** with the migration CLI in SQLite mode. Source must have the current Phase 24R columns
   and legacy schema version 1. A migration ledger is optional for a legacy source; if present,
   every recorded identity must be known. Unknown tables, incompatible/missing required columns,
   incompatible column types/primary keys,
   failed integrity/FK checks and obvious email uniqueness conflicts cause refusal.
3. Create an isolated empty PostgreSQL destination and run the schema CLI there. Set the
   secure PostgreSQL `DATABASE_URL` and require-Postgres flag. Import never creates/upgrades
   the destination schema. Optional absent source tables are legacy `rag_chunks` and lazily
   created `support_ticket_messages`; all other supported data tables must exist.
4. Run preflight first, with an explicit source path:

   ```text
   python -m app.database.import_sqlite --source /BACKED_UP_WORKING_COPY/valyqon.sqlite --dry-run
   ```

   Dry-run opens the source with URI `mode=ro`, query-only, and a read transaction. It checks
   the fully migrated destination and empty-data guard without DDL, data/marker writes or
   sequence updates. It reports only fixed table names and counts. Schema comparison creates
   a canonical SQLite reference only in an isolated temporary directory.
5. After reviewing the counts and backup/rehearsal results, explicitly execute:

   ```text
   python -m app.database.import_sqlite --source /BACKED_UP_WORKING_COPY/valyqon.sqlite --execute
   ```

   One destination transaction covers all tables, count verification and import marker.
   Tables follow fixed parent-before-child ordering; each table is read in primary-key order
   and batched in groups of 500. Explicit IDs, ownership boundaries, timestamps, serialized
   JSON, binary vectors and stored hashes/tokens are copied unchanged. Nothing prints their
   values. Identity sequences are reseeded above imported IDs. `setval` is nontransactional:
   failure can leave harmless sequence gaps, while rows and the marker roll back together.
6. Verify per-table counts, expected scoped records, FK integrity, one-time tokens, sessions,
   organization/role/invitation behavior and creation of new records above imported IDs in
   a protected staging environment. Take and verify a new PostgreSQL backup before admitting
   production traffic. Rehearse recovery as well as the successful import.

The tool refuses any populated destination or completed import marker. It never merges,
truncates, overwrites or silently duplicates data, even on an accidental second invocation.
Generic CLI failures intentionally hide raw details. Use schema/version/empty-database
checks and protected operator investigation rather than publishing database contents.
The marker fingerprint is an operational marker, not a cryptographic logical-data checksum
for a live/WAL database. Writers must stay stopped through the entire procedure.

## PostgreSQL backup and restore

Use maintained PostgreSQL `pg_dump`/`pg_restore` tools appropriate to the server version.
An operator provisions protected libpq service configuration and password storage (for example
`PGSERVICEFILE` plus `PGPASSFILE`, with restricted filesystem permissions). Never embed a password
in scripts/commands. The named services below are placeholders configured separately; service
files contain connectivity metadata and should not be shared as public diagnostics.

Backup wrapper commands (operator-run only):

```text
pg_dump --dbname=service=VALYQON_BACKUP_SERVICE --format=custom --no-owner --no-acl --file=/PROTECTED_BACKUPS/valyqon.dump
pg_restore --list /PROTECTED_BACKUPS/valyqon.dump
```

Require exit code 0, a nonempty archive and successful archive listing. Record a checksum and
backup time, encrypt/protect off-host copies, and apply retention/access policies. Listing alone
does not establish restorability: regularly restore into an **independent empty validation
database** and compare counts, migration identities, scoped records and schema constraints.
PostgreSQL backup does not include Qdrant/files; coordinate their recovery points separately.

Restore requires an explicit operator decision and a newly provisioned empty validation/recovery
database. Verify the restore service points to that database, never to the live database:

```text
pg_restore --dbname=service=VALYQON_EMPTY_RESTORE_SERVICE --single-transaction --exit-on-error --no-owner --no-acl /PROTECTED_BACKUPS/valyqon.dump
```

No `--clean`, DROP database or destructive automatic restore wrapper is provided. Stop writers
before an approved recovery, restore first to a separate target, verify data/schema/migrations,
tenant isolation, authentication and health, then explicitly select the recovered database.
Review role grants/ownership omitted by the portable archive flags before enabling traffic.
Retain the failed database/backup for protected investigation; do not erase it automatically.

## Rollback and production cutover checklist

- Before cutover: verified SQLite/Qdrant backups, restored PostgreSQL rehearsal, isolated real
  driver/server tests, Phase 24S.2 regression/security/load review, TLS/grants/connection budget,
  and a tested rollback window. No such production action was performed in 24S.1A.
- Select the PostgreSQL URL and require-Postgres flag together. The optional
  `compose.postgresql.example.yaml` demonstrates an external-PostgreSQL override for **both**
  API and bot. It adds no database service. It must be explicitly selected after deployment
  review; existing Docker/Compose defaults and production infrastructure remain unchanged.
- Stop writers, verify backups, migrate the empty destination, dry-run, execute import,
  compare counts and ownership, restore-test a PostgreSQL backup, verify API/bot health and
  scoped authentication/workflows, then admit traffic and observe it.
- Before admitting PostgreSQL writes, rollback may select the untouched SQLite backup and
  compatible application configuration. After PostgreSQL accepts new writes, do not simply
  switch back to an old SQLite snapshot: that loses data. Prefer restoring PostgreSQL or
  rolling back to a PostgreSQL-capable application build while retaining PostgreSQL.
  Phase 24R code cannot operate PostgreSQL. Reverse migration/reconciliation
  requires a separate operator-reviewed plan; no automatic downgrade/export is supplied.

## Verification and known limits

Set `VALYQON_EMAIL_MODE=disabled` in the test process. Tests use temporary SQLite fixtures,
mocked delivery/providers/sources and pool fakes; no real email, AI or procurement calls occur.

```text
python -m pytest tests/test_postgresql_foundation.py -q
python -m compileall -q app tests
git diff --check
```

The persistence-domain validation includes auth/accounts/sessions and Telegram linking,
verification, reset, organization roles/invitations, companies, saved opportunities,
search history, monitoring, support, analyses and RAG. Billing has no persistence to test.
The known deferred test remains
`tests/test_monitoring.py::MonitoringTests::test_service_uses_owner_specific_profile_terms`;
deselect only that test during focused validation. A clean full regression is reserved for
the subsequent review/24S.2, not automatically run here.

`POSTGRES_INTEGRATION_TESTED=NO`: this environment has neither psycopg/psycopg_pool nor
PostgreSQL CLI tools or a verified isolated server. Config, generated dialect/schema SQL,
pool acquire/release/rollback/redaction/lifecycle, migration ordering/idempotence/rollback,
import safety/value preservation and SQLite concurrency were tested without a server.
Import algorithm fixtures use SQLite underneath and explicitly do **not** count as PostgreSQL
integration. Actual driver/server DDL, identity/bytea behavior, expression indexes, advisory
locks across processes, real pooled network failures, sequence reseeding and pg_dump/restore
remain operator integration steps before cutover. No package was installed to bypass this limit.

Scope exclusions remain Redis/cache, queues/workers, AI routing/dedup, connector workers,
RAG scale, scoring separation, quota/fair usage, observability, payments, Supplier Intelligence,
the Monitoring matcher, unrelated UI changes, commit/push and production deployment.

### Final local validation record

With `VALYQON_EMAIL_MODE=disabled`, final persistence/security/deployment validation passed
**321 tests, 11 subtests**, with **1 deselected**, **0 skipped**, **0 failures** and one existing
Starlette/httpx deprecation warning (219.29 seconds). The final health/foundation follow-up
passed **59 tests**, **0 skipped**, **0 failures**, one warning (8.80 seconds).
The foundation module contains **48 server-independent tests**. Compilation and
`git diff --check` returned 0. No full-suite regression was run.

The exact final broad selection was:

```powershell
$env:VALYQON_EMAIL_MODE = 'disabled'
$persistenceTests = @(
  'tests/test_postgresql_foundation.py', 'tests/test_auth.py',
  'tests/test_auth_api.py', 'tests/test_auth_owner_link_migration.py',
  'tests/test_auth_rate_limit.py', 'tests/test_session_access.py',
  'tests/test_password_reset.py', 'tests/test_password_reset_api.py',
  'tests/test_email_verification.py', 'tests/test_email_verification_api.py',
  'tests/test_organizations.py', 'tests/test_organization_api.py',
  'tests/test_organization_invitations.py', 'tests/test_organization_companies.py',
  'tests/test_organization_data.py', 'tests/test_organization_pdf_rag.py',
  'tests/test_organization_workflows.py', 'tests/test_companies.py',
  'tests/test_company_management.py', 'tests/test_shortlist_repository.py',
  'tests/test_shortlist_integration.py', 'tests/test_shortlist_api_behavior.py',
  'tests/test_discovery_history_repository.py', 'tests/test_discovery_history_api_behavior.py',
  'tests/test_monitoring.py', 'tests/test_support.py', 'tests/test_database.py',
  'tests/test_rag.py', 'tests/test_api.py', 'tests/test_bot.py',
  'tests/test_deployment.py', 'tests/test_telegram_link_concurrency.py',
  'tests/test_phase17_security_hardening.py'
)
python -m pytest @persistenceTests -q --deselect tests/test_monitoring.py::MonitoringTests::test_service_uses_owner_specific_profile_terms
python -m pytest tests/test_api.py tests/test_postgresql_foundation.py -q
python -m compileall -q app tests
git diff --check
```

The existing isolated Python 3.12 environment was reused without installing dependencies or
changing the global environment. Missing PostgreSQL integration is the remaining external
verification requirement; it does not hide an implementation blocker, and it must be resolved
before the later production cutover. Real network/pooling/DDL/import/backup behavior has not
been claimed as verified here.
