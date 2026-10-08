# Phase 24S.1G — Connector Workers

Starting branch: `phase24-professional-saas-core`. Verified clean worktree and
HEAD `495be85498d93831d5f9912425f28c6ebb109cc0` before editing. No production
deployment, external source/provider/server calls, secret search, commit or push.

## Pre-change audit

`app/sources/base.py` defines a runtime-checkable `TenderSource` Protocol:
`name: str` property and `async fetch(limit: int = 20) -> list[TenderNotice]`.
`app/sources/models.py` defines the frozen dataclass `TenderNotice` with required
`source`, `external_id`, `title`, `url`; optional `published_at`, `tender_number`,
`customer`, `initial_price`, `currency`, `deadline`, `region`, `summary`.
Its `identity` property is `(source, external_id)`. There are no category,
document, source-updated or cursor fields in this normalized contract.

`SourceRegistry` validates server source keys against
`^[a-z0-9][a-z0-9_-]{0,63}$`, matches adapter name to key, rejects duplicate keys,
and raises `SourceRegistryError` for unknown keys. Construction does not fetch.
`build_source_catalog(MonitoringSettings)` explicitly constructs these adapters:

| ID / module | Existing fetch/normalization behavior | Existing body/page limits |
| --- | --- | --- |
| `eis` / `eis_rss.py` | Operator HTTPS URLs; RSS 2.0/Atom XML; GUID, procurement number, or SHA-256 deterministic fallback identity. HTML highlighting/business metadata are cleaned. `for_search_terms` builds official EIS RSS query URLs. | 5 MiB per feed; static feed count was not capped; generated profile feeds 1–20, default 5. |
| `ted` / `ted_api.py` | POST official v3 Search API JSON; publication-number identity; ACTIVE scope, `OJ = () SORT BY publication-date DESC`; page 1. | 10 MiB; single page. |
| `sam_gov` / `sam_gov_api.py` | GET official Opportunities API JSON; noticeId identity; offset 0; default seven-day posted-date lookback (configured adapter range 0–365 days). Operator `SAM_GOV_API_KEY` query credential. | 10 MiB; single page. |
| `uk_fts` / `uk_fts_api.py` | GET official OCDS release packages, tender stage; release-ID identity; procurement URL based on OCID. | 10 MiB; single request. |
| `canada_buys` / `canada_buys_dataset.py` | GET official open-notices UTF-8 CSV; reference-number identity; solicitation and bilingual notice/description fields; public search URL fallback. | 25 MiB; single dataset, normalized output capped. |
| `austender` / `austender_rss.py` | GET official current-ATM RSS then ATM detail HTML; validated official UUID URLs, no Advert records; buyer, amount, ACT-local deadline normalization. | 5 MiB/feed or detail; one listing plus up to limit details; concurrency default 5, configured 1–20. |
| `nz_gets` / `nz_gets_rss.py` | GET official RSS XML; RFx identity/canonical public URL and business fields. | 10 MiB; single feed. |
| `za_etenders` / `za_etenders.py` | GET official active-opportunities JSON; normalize public tender identity/business metadata; SAST dates retain established semantics. | 15 MiB; single request. |
| `india_cppp` / `india_cppp.py` | GET HTML listings and source-provided next links; Tender ID identity; IST dates; detects repeated pages/conflicting duplicate IDs. | 2 MiB/page; 50-page pre-change loop (could fetch an unused next page at its final iteration). |
| `kz_goszakup` / `kz_goszakup.py` | GET official Open API JSON with operator bearer token `KZ_GOSZAKUP_API_TOKEN`; announcement-ID identity; exact official host/path next-page validation; duplicate/repeated-page protection. | 10 MiB/page; 20-page hard maximum. |

All adapters clamp requested notice limits to 1–100. They use HTTPX async clients
with timeouts, TLS verification, environment/proxy trust, and followed redirects
(HTTPX default redirect maximum 20). Catalog construction passes
`MONITOR_REQUEST_TIMEOUT` (default 30 seconds, validated >0 and <=120); adapter
defaults are 30 seconds for EIS/TED/SAM/UK/KZ, 45 for Canada/AusTender/GETS, 60
for India/South Africa. EIS supports an operator CA bundle. Existing bodies were
checked after client buffering; transport/HTTP failures were sanitized into
`SourceError`, losing retry/status distinctions. There were no adapter retry
loops or reusable persistent source cursors/delays. SAM/KZ credentials belong
to operators; these are public datasets, not tenant-specific private sources.

`SourceCatalog.fetch` wraps `MultiSourceFetcher` (default source concurrency 8,
bounded 1–32), optionally cloning EIS for profile terms. Fetcher validates source
identity, external ID and URL presence, deduplicates `(source, external_id)`,
round-robin merges source lists, and returns safe structured statuses/failures.
There is no B2B-Center procurement adapter/registry entry. The B2B string in LLM
configuration is a GigaChat scope, unrelated to procurement. Production's only
fake-like adapter is `_UnavailableSource`, a disabled SAM/KZ placeholder.
Deterministic fake/dynamic sources already exist in source/monitoring tests.

`TenderMonitorService.fetch_matches_from_catalog_for_profile` supplies company
monitoring keywords and profile-feed limit to catalog, then applies the existing
`prefilter_notice`. Organization Discover's authenticated, same-origin-guarded
POST `/api/v1/organizations/{organization_id}/discover/tenders` waits for that
live fetch. Other owner/bot discovery and on-demand monitoring paths also use
the existing service. Background subscription monitoring is EIS-only, uses
owner-specific profile resolution, and deduplicates through `monitor_seen`
using owner/source/external identity and company-specific source suffixes.
No Monitoring matching/service/test implementation is changed in this phase.

Source Health's organization GET `/discovery/source-health` does not probe
sources. It reads the active company's `discovery_search_history` snapshots,
catalog metadata, and safe status messages. `app/sources/health.py` is an explicit
live EIS smoke CLI, not persistent worker telemetry; it was not run.

`tenders` persists tenant/owner private PDF analyses. `saved_opportunities`
persists organization/company snapshots with scoped unique source identity.
`discovery_search_history` persists tenant search results and health snapshots.
None is a shared public ingestion store. `monitor_seen` is notification
deduplication, not a normalized notice repository. Source correctness had no
Redis dependency or shared cache integration; this phase adds none.

Phase 24S.1C has `JobScope(account_id=None, organization_id=None, company_id=None)`
and nullable foreign keys. All-NULL scope already represents system work;
repository scope filters use **exact `IS NULL`**, never wildcard matching.
Idempotency is hashed over type, exact scope values, and caller identity, with a
partial unique index covering queued/running/succeeded jobs. Worker leases have
hashed random tokens, heartbeat, authoritative DB time and fenced completion/
failure; expired jobs replay with bounded attempts/backoff. `HandlerRegistry`
requires explicit synchronous handlers. Phase 24S.1F's CLI selected `--rag` only.
API RAG status routes build authenticated tenant scope and cannot see system
connector jobs. No generic customer job enumeration exists.

DB migrations are additive/checksummed; versions 1–9 were auth, organizations,
companies, tenders, monitoring, rag, support, operations, jobs. SQLite uses
transactional `BEGIN IMMEDIATE`; PostgreSQL uses the project's DB-API SQL
translation and controlled write/advisory locks. The offline importer maintains
an explicit table allowlist. Docker's current API/bot commands do not launch job
workers; no Docker/startup deployment configuration was changed.

## New architecture and wire contracts

Approved catalog source -> `ConnectorSyncService` -> `connector.sync.v1` durable
system job -> `ConnectorSyncHandler` -> bounded existing adapter -> validate/
deduplicate -> `OpportunityRepository` -> shared `source_opportunities` ->
optional snapshot Discover. No LLM, scoring, embeddings or notifications run in
the handler. Existing discovery scoring remains outside this worker.

Exact payload example (no extra keys accepted):

```json
{"schema":1,"source_id":"ted","sync_window":"2026-10-08T12Z","connector_version":"connector-sync-v1:ted:adapter-r1"}
```

Exact result example:

```json
{"schema":1,"source_id":"ted","sync_window":"2026-10-08T12Z","fetched_count":3,"accepted_count":1,"skipped_count":2,"inserted_count":1,"updated_count":0}
```

Fetched count is the adapter list length. Accepted count counts unique validated
rows successfully persisted in this attempt. Skipped counts invalid or duplicate
rows. Inserted/updated distinguish the insert winner from existing-row updates;
updated includes replaying an unchanged row. Counts describe this attempt, not
the sum of failed attempts. Results contain no notice arrays, responses or keys.

Connector version is `connector-sync-v1:{source_id}:adapter-r1`; increment adapter
revision when normalization materially changes. No timestamp or credential is
part of version identity. Registry reuse avoids dynamic import/class/URL routing;
the worker's static host map is an endpoint policy, not a second adapter registry.
Disabled/unknown sources fail permanently. EIS shared sync requires static feeds;
profile-generated company terms never enter shared ingestion.

Window formula is `aware_time.astimezone(UTC).strftime('%Y-%m-%dT%HZ')`, a UTC
hour slot. Operator enqueue always uses the current time, accepts no window or
historical-crawl option. An in-process aware clock seam exists for tests. Payload
windows are exactly 14 characters and calendar-validated. Window is a logical
run identity, not an upstream historical cursor or immutable source snapshot;
retries fetch the source's current bounded discovery slice.

Service idempotency key is compact JSON `[source_id,sync_window,connector_version]`.
Repository fingerprint is SHA-256 of compact ASCII JSON
`["connector.sync.v1",[null,null,null],idempotency_key]`. Same logical slot reuses
queued/running/succeeded work; the next hour is refreshable. Failed/cancelled
identities follow existing explicit re-enqueue semantics. No scheduler is added.

## Persistence, validation and replay

Migration **10**, domain **opportunities**, checksum
`95f679368a7c292f931d8b84e44ca3dec9a1c2970223f11b202337340962298b`.
Historical migration SQL/checksums are unchanged. New schema:

```sql
source_opportunities(
  source_id TEXT NOT NULL CHECK(length(source_id) BETWEEN 1 AND 64),
  external_id TEXT NOT NULL CHECK(length(external_id) BETWEEN 1 AND 500),
  notice_json TEXT NOT NULL,
  connector_version TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  PRIMARY KEY(source_id, external_id)
)
```

Index `idx_source_opportunities_recent(source_id,last_seen DESC,external_id)`.
`notice_json` contains only the exact 13 TenderNotice dataclass fields above,
never the raw HTTP response or tenant profile. This small shared repository
avoids repurposing private/scoped tables. No invented category/source cursor
fields. The importer accepts old pre-10 databases without this optional table,
transfers it when present, and rejects a claimed migration 10 with a missing
table. Both DDL and parameterized repository SQL use the existing PostgreSQL
translation. Real PostgreSQL was not contacted.

Identity is `(source_id, external_id)`; use the adapter's stable existing ID,
including EIS SHA-256 fallback. No title dedup across sources, Python `hash`, or
random notice identity. Each row transaction does `INSERT ... ON CONFLICT ... DO
NOTHING`, then `UPDATE ... WHERE source_id=? AND external_id=?` on conflict under
the existing DB write transaction. This preserves `first_seen` and updates notice
fields, provenance and `last_seen` in UTC. Unique constraints and serialized
writes make concurrency duplicate-free. Partial commits remain and replay safely
updates them. Source-local dates/deadlines retain their strings/timezone semantics;
internal first/last timestamps use aware UTC ISO strings.

Validation requires correct registered source, nonempty stable ID/title/URL;
source 64, ID/tender-number 500, title 1000, URL/customer/region 2000, summary
4000, date strings 120 characters; no NUL, invalid HTTP(S) URL, userinfo,
whitespace/fragment, known credential-query keys, or unnormalized HTML in
normalized text fields. Currency is uppercase three letters. Amount must be
finite, numeric, nonnegative and <=1e18. Dates accept established ISO, RFC feed
dates and EIS `DD.MM.YYYY[ HH:MM]` without reinterpreting naive source times.
Other malformed human-readable source dates are skipped rather than stored.
Invalid individual rows are skipped with bounded counts; invalid batch contract,
parser/configuration/provenance or identity routing fails permanently.

Existing lease tokens, heartbeat and completion/failure fencing are unchanged.
Handler checks shutdown/lease loss before every write. Stale work might have
committed public rows before losing its lease; replay upserts the same identities
and stale completion is rejected. This is **at-least-once execution**, not
exactly-once delivery. No notices are deleted on failed sync or absence.

## Bounds, security and failures

`VALYQON_CONNECTOR_MAX_RECORDS` is implemented, default **20**, range **1–100**.
Oversized adapter lists fail rather than being persisted. Workers fetch one
source per job, at most **5** EIS feeds/India pages/KZ pages, **1** listing/feed/
dataset for other sources, or **1 + max_records** AusTender requests (default
21). AusTender worker detail concurrency is **1**. No recursive crawling or
thread-per-page orchestration. India/KZ stop at the worker page bound and store
the bounded slice. Live India retains its 50-page loop but no longer makes an
unused final-page request; live KZ retains 20 pages and its existing error policy.

Worker HTTP timeout is min(adapter timeout, **30 seconds**); total fetch budget
**180 seconds**. Worker redirects are **0**, all 3xx fail permanently. Requests
must be HTTPS, without userinfo, at default/443 port, and exactly match server
host policy; source-provided pagination/detail URLs pass this check too. EIS
worker accepts official `zakupki.gov.ru`/`www.zakupki.gov.ru` only. Existing custom
operator EIS URLs remain compatible on live paths but are deliberately rejected
by shared worker ingestion. No customer URLs or endpoint settings exist here.
TLS verification, operator CA and proxy trust remain; certificate verification
is never disabled. Streaming decoded response limit **25 MiB** prevents whole
unbounded bodies; adapter-specific smaller checks remain (table above).

| Condition | Durable outcome |
| --- | --- |
| HTTPX transport/network/OS error, timeout or total fetch timeout | Retryable |
| HTTP 408, 429, 500–599 | Retryable |
| Temporary DB `StorageError` / SQLite `OperationalError` | Retryable |
| Cooperative shutdown/lease-loss interruption | Retryable, subject to valid lease proof |
| HTTP 401/403 or other non-2xx including redirect | Permanent, operator intervention |
| Unknown/disabled source, unsafe endpoint, malformed payload/window/version, missing static EIS configuration | Permanent |
| Parser/schema error, `SourceError`, invalid batch type or oversized list, body/request bound violation | Permanent |
| Constraint/integrity storage error | Permanent |
| Individual malformed normalized row | Skip, increment bounded count |

Retry policy comes only from durable jobs: default **3 attempts**, configurable
existing job maximum **1–20**, deterministic delay
`min(300, 2**min(attempt_count-1,9))` seconds. Transport itself adds no retries.
Errors persist only existing allowlisted failure codes; messages/raw bodies/
URLs/headers are not persisted or printed by connector CLI/handler/worker.

Admission permits **one running connector lease globally**, stricter than a
per-source cap. SQLite admission uses `BEGIN IMMEDIATE`; PostgreSQL serializes
short claim transactions with dedicated transaction advisory key **240003**, then
uses existing `FOR UPDATE SKIP LOCKED`. All claimers use this gate; heartbeats,
completion and network work do not hold it. Other job types can run during a
connector execution. Pools claim only their explicitly registered types so RAG
workers cannot accidentally fail connector jobs as unknown types. Lease replay
can temporarily overlap stale execution; bounded fetching/cooperative checks and
idempotent storage remain the correctness mechanism. No distributed scheduler,
tenant quotas, Redis correctness dependency or new metrics system was introduced.

## Operation and staged adoption

```text
python -m app.jobs.worker --connectors
python -m app.jobs.worker --rag
python -m app.jobs.worker --rag --connectors
python -m app.sources.enqueue --source ted
python -m app.sources.enqueue --status <job-uuid>
```

Reverse flag order also works. No flag, unknown or duplicate flags refuse before
storage. Production handlers are explicit; web never auto-starts a pool.
Graceful stop/lease fencing and storage-lifetime safety remain unchanged.
Connector-only startup does not initialize RAG/provider/vector services.

The enqueue CLI is the real operator path, with OS/process/database permissions
as its authorization boundary. Organization owners are not global procurement
operators, so there is intentionally **no customer refresh HTTP API**. CLI accepts
source ID or job UUID only, exposes job ID/state and safe result counts/failure
code, not payload/lease/stack trace. System jobs cannot be read or cancelled with
customer scopes; no fake accounts and no scope schema change.

Default Discover remains live and profile-aware. The existing authenticated POST
can explicitly use `?snapshots=true`, selecting a catalog-compatible local
`SnapshotSource` for each approved enabled source. It reads at most **1000** recent
candidates/source and returns **1–100**/source; EIS profile-term preselection and
the unchanged downstream profile matcher preserve local matching semantics as
closely as a bounded public snapshot allows. Header
`X-Valyqon-Discovery-Mode: snapshots` identifies the staged mode. No external
fetch/wait/fallback or automatic enqueue occurs. Worker store is canonical for
snapshot ingestion; live catalog remains canonical for the compatibility path.
Broad snapshots cannot provide full historical/provider keyword coverage; an
empty store returns an empty successful local read, not an automatic live crawl.

Monitoring stays on its existing live/profile-specific EIS path. No matcher,
notification or scoring implementation changed, including the deferred known
`tests/test_monitoring.py::MonitoringTests::test_service_uses_owner_specific_profile_terms`.
Snapshot adapters can be reused later; automatic Monitoring migration is deferred.

Source Health still persists/readbacks company Discover snapshots. Connector jobs
do not write tenant history or introduce a new health table. Default live statuses
are unchanged. Snapshot-mode statuses describe local store reads, **not a fresh
remote source probe**; its recorded `last_checked` is the Discover read time. Job
status is the operator's safe sync completion/failure view.

Operational prerequisites: writable configured project DB, additive migration 10,
separately supervised explicit worker and operator enqueue, approved source/TLS/
proxy connectivity in the future real environment; configured operator keys for
SAM/KZ and static official EIS feeds if selected. Docker deployment remains
untouched. No new dependencies. Migration rollback follows existing backup/
restore convention; do not edit/delete historical ledger entries in place.

## Offline validation and status

`scripts/validate_connector_workers.py` reuses `validate_ai_gateway.py`'s explicit
external DNS/socket guard: external `getaddrinfo`, `connect` and `connect_ex` fail
closed; local TestClient/Windows asyncio loopback stays allowed. It requires
explicit `tests/test_*.py` filenames and has no full-suite default. It sets
`VALYQON_EMAIL_MODE=disabled` and `VALYQON_AI_FALLBACK_ENABLED=false`.
Fakes exercise actual registry/service/handler/repository/worker; HTTP adapter
tests inject `httpx.MockTransport` at the client boundary, not handler output.
Tests cover source IDs, URL/module/traversal injection, exact payload/results,
current/future slots, concurrent enqueue/claims, validation, shared unique IDs,
updates, partial persistence retry, lease replay/fencing, 401/403/408/429/5xx,
timeouts/network errors, streamed body bounds, actual India/KZ/EIS page bounds,
safe operator enqueue/status, connector/combined CLI, existing RAG CLI, local
Discover API auth/CSRF/isolation and live compatibility, PostgreSQL SQL generation.
Existing source/catalog/health/Discover/jobs/database/security tests are also run.

Real integrations remain **unverified/offline-only**. No real procurement, Groq,
GigaChat, Redis, PostgreSQL or Qdrant server was contacted. No production change,
deployment, commit or push. No full suite was run. The known Monitoring matcher
is excluded from focused passing validation and remains deferred to 24S.2.
Phase 24S.1H can consume normalized public notices for separated scoring; no
24S.1H/1I/1J/24S.2/24T/Phase25 work is included.

Final focused run: **372 passed, 1 skipped, 1 deselected**, exit **0**; **67**
new connector tests passed. One existing Starlette TestClient deprecation warning.
The sole deselection is the known Monitoring matcher, via process-local
`PYTEST_ADDOPTS='-k "not test_service_uses_owner_specific_profile_terms"'`.
Exact focused command (with the two disabled environment flags above):

```text
python scripts/validate_connector_workers.py tests/test_connector_workers.py tests/test_jobs.py tests/test_rag_ingestion.py tests/test_source_catalog.py tests/test_source_framework.py tests/test_austender_source.py tests/test_ted_source.py tests/test_canada_buys_source.py tests/test_eis_business_metadata.py tests/test_india_cppp_source.py tests/test_kz_goszakup_source.py tests/test_nz_gets_source.py tests/test_sam_gov_source.py tests/test_uk_fts_source.py tests/test_za_etenders_source.py tests/test_monitoring.py tests/test_database.py tests/test_postgresql_foundation.py tests/test_discovery_history_api_behavior.py tests/test_source_health_api_behavior.py tests/test_organization_workflows.py tests/test_session_access.py tests/test_phase17_security_hardening.py tests/test_api.py
python -m compileall -q app tests scripts
git diff --check
```

Compile exit **0**; whitespace exit **0**. This Windows shell's `python` alias was
unavailable; these commands were executed with the existing project interpreter
`C:/Users/ramze/Documents/Codex/tender-ai/.venv/Scripts/python.exe` (Python 3.12.14),
without installing dependencies or altering that environment. `rg` was unavailable;
audit searches used tracked-file listings, PowerShell reads and `git grep`.
No implementation blocker remains; live upstream behavior and real PostgreSQL
integration remain operational verification tasks outside this offline phase.
