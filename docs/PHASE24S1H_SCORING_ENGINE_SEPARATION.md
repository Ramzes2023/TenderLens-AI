# Phase 24S.1H — scoring engine separation

## Architecture audit (recorded before implementation)

`app/scoring/engine.py::score_tender` is already a provider-neutral, deterministic
document fit engine. Weights: category 30, region 15, budget 20, bid security 10,
contract security 10, documents 15. Missing facts leave the denominator; fit is
earned/scorable weight × 100, rounded to one decimal (or null if nothing is
scorable). Document matches can be partial; hard stops are independent of score.
Completeness counts ten factual groups. Currency normalization is shared; no
conversion or win probability is inferred.

Organization Discover has a second existing formula in
`organization_workflow_routes.py::_metadata_preview_scoring`: product matches in
title/object/context give 70/60/35, supply intent adds 10, contextual service-only
matches cap at 20, final range 0–90. Labels: matched at 65+, partial above zero,
failed at zero. It retains the document engine's other criteria and explanations.
The browser sorts score descending, then completeness descending with stable
input order. Existing HTTP document scoring, saved PDF scoring, and bot scoring
call `score_tender`; shortlist and discovery history save customer snapshots.
No existing dedicated durable scored-result repository was found.

Discover uses `prefilter_notice`: exclusions, search_keywords (fallback product
keywords), comparable single-currency budget limits, and region hard stops.
The Unicode phrase matcher uses exact Latin tokens and conservative Russian
stems. Currency mismatch explains rather than prefilter-rejecting. Industry,
business_mode and allowed_countries exist in CompanyProfile but these engines do
not currently use them; this phase must not invent rules for them. Monitoring
uses the same matcher and remains unchanged, including its deferred failure.

Company workspaces persist mutable validated profile JSON with a user-provided
profile_version; there is no immutable profile history. Membership is checked
by company/organization repositories: viewers read; owner/admin/member mutate.
Account, organization and company form JobScope. Queue scope validation checks
stored parents but application authorization is still required. Durable jobs use
leases, hashed tokens, retry backoff, explicit handlers and fenced completion.
RAG workers and connector workers are explicitly selected by CLI, never web
startup. Connector ingestion stores only normalized public TenderNotice data in
source_opportunities. Migration 10 creates that mutable public store; snapshot
catalog reads at most 1000 recent rows per source and filters locally before
returning at most 100. No HTTP fallback exists. Database adapter supports SQLite
and generated PostgreSQL SQL; the explicit importer uses a fixed table list.

Pre-change flow: source fetch → relevance filter → API metadata scoring → HTTP
response/history; document extraction/AI → deterministic document scoring.
The frontend consumes existing ScoringResult criteria, fit and completeness;
its behavior and thresholds must stay unchanged. AI document analysis and the
GigaChat/Groq gateway/cache are separate and will not be edited.

## Implemented boundaries and flow

* Public ingestion remains `ConnectorSyncHandler` → `source_opportunities`.
  It never loads company profiles or calls a scoring function.
* `ScoringRunService.enqueue` resolves membership/company/profile from stored
  parents, selects bounded local candidates and freezes their public revisions.
* `scoring.preview.score_metadata_preview` is the exact extracted Discover
  function; `scoring.engine.score_tender` remains the original document scorer.
  The old API name is retained as an import alias for compatibility.
* Explicit `ScoringRunHandler` reads the frozen references, revalidates the
  profile digest and stored authorization, applies the existing prefilter,
  computes metadata scores serially, then materializes private results.
* `ScoringRunService.view` checks the authorized account/organization/company,
  current profile identity and job success before presenting a bounded page.
* Document AI/PDF/RAG analysis remains a separate later application operation;
  scoring workers neither fetch procurement data nor generate AI reports.

Post-change opt-in flow: authenticated company request → immutable bounded
snapshot references → `scoring.run.v1` → explicit worker → existing relevance
filter/metadata engine → private rows → fenced job success → authenticated page.
Existing synchronous Discover, Global Discover, document scoring, saved
opportunities, search history, Monitoring and dashboard consumers retain their
current contracts. No frontend changes, thresholds, weights or matcher fixes.

## Computation identity and snapshots

Engine version is `scoring-engine-v1`. Profile identity is SHA-256 of canonical
validated CompanyProfile JSON (including its declared version and every scoring
setting). Raw profile JSON is read only from the existing company workspace; it
is never copied into queue payloads, keys or shared public storage. A digest
handles edits even when customers do not bump the declared profile_version.

Public revision = SHA-256(canonical `[TenderNotice fields, connector_version]`).
Snapshot identity = SHA-256(canonical `[JobScope.values, profile_digest,
engine_version, selection_configuration, examined_public_revision_references,
selected_revision_ids]`). Canonical JSON sorts keys, uses compact separators,
UTF-8 and finite numbers. Python hash() is never used. Queue idempotency then
uses its existing SHA-256 over `[job_type, scope.values, snapshot_identity]`.
The exact run can reuse a queued/running/succeeded job; failed/cancelled jobs
release that active identity. Time alone does not freeze or invalidate scoring.
Changed profiles, source content/provenance, selection configuration or bounded
pool order produce a different identity. Changes outside the bounded pool are
deliberately outside that run's computation identity.

Mutable source_opportunities cannot support repeatable delayed work alone.
Migration 11 therefore adds shared, content-addressed **public** revisions and
private snapshot/candidate references. It copies each selected public revision
once, not once per tenant or retry; no private score/profile is stored there.
Selection runs in the existing adapter's explicit transaction, serializing with
ingestion writes. Workers use frozen revisions even if ingestion later changes
the source row. Current profile is checked before computation, before writes
and at retrieval. Changed profiles return HTTP 409 and require a new run;
unprocessed stale-profile jobs fail permanently. Old results are never presented
as scores for the new profile. Source changes leave the explicitly identified
historical snapshot readable until the profile changes.

## Candidate and output bounds

Request accepts 1–5 distinct known source IDs and 1–100 candidates per source
(defaults: `ted`, 20). Known IDs are the existing ten connector IDs. Selection
uses the indexed latest 1000 rows per source, ordered by last_seen descending
then external_id, and the same local substring keyword selection as
OpportunityRepository.read (first 20 search terms, falling back to products).
No full-history scan or arbitrary URL exists. It then freezes at most 500
references; workers read at most 501 to detect corrupted bounds. Candidate
order is canonical source ID order followed by the frozen per-source order.
Scores sort descending, then completeness descending, then frozen ordinal.
Matching and exclusions use existing prefilter_notice, without changing it.

This preserves the current **snapshot** keyword/filter semantics. A bounded
locally synchronized pool cannot promise the same recall as live source-specific
keyword searches. No source auto-sync or HTTP fallback is attempted. Source
state is `available` for a nonempty examined pool, or
`empty_or_not_synchronized`; this is local availability, not live source health.
An empty completed run returns zero results, with that explicit source state.
Metadata language and all factual source fields survive in public revisions;
analysis_from_notice maps only supported facts, without fabricated documents,
security percentages, risks or technical requirements.

One worker processes candidates serially; the existing small bounded WorkerPool
controls concurrency. There is no per-tender thread or LLM call. Each stored
customer scoring JSON is bounded to 32768 bytes. Retrieval limits are 1–100
(default 50), offsets 0–500, total results at most 500. Only references and the
existing score, criteria, explanations, hard stops and completeness are returned,
plus computation digests/version and explicit completion/source state. Company
name/declared profile text version, raw metadata/tender bodies, documents,
prompts and reports are omitted. Existing explanations/evidence may contain
matched private keywords or constraints; these belong only to authorized private
result pages, never the durable job result or public stores.

## Scope, API and privacy

Endpoints (no global job enumeration):

```
POST /api/v1/organizations/{organization_id}/companies/{company_id}/scoring/runs
GET  /api/v1/organizations/{organization_id}/companies/{company_id}/scoring/runs/{job_id}?limit=50&offset=0
```

POST body: `{"sources":["ted"],"limit_per_source":20}`. POST returns HTTP 202
with safe job ID/state and computation metadata, without running the scorer.
GET returns state and completion together with a bounded result page. Both
authenticate through current_account and use existing organization membership
and company service boundaries. The persistent service also rechecks stored
active account, membership and company relation. POST requires existing
same-origin/CSRF protections; responses are no-store. Unknown/wrong-scope jobs,
revoked membership and missing company are inaccessible. Invalid/stale profile
identity is HTTP 409; unavailable storage is a sanitized 503; malformed request
bounds use FastAPI 422. No error contains profile/tender text or stack traces.

Viewer/admin/member/owner may enqueue and retrieve their own computations,
consistent with existing organization metadata Discover and scoring/evaluate
permissions (company mutation and monitoring have stricter permissions).
Results are additionally account-scoped, as the existing JobScope contract is;
another member cannot read the initiator's job by guessing its ID. Each member
can enqueue the same company selection under their own authorized account.
Company is explicit in the route and stored scope; switching the active company
does not retarget existing jobs. No payload organization/company IDs authorize
access. The existing migration 9 FK restricts normal deletion of a company while
durable jobs reference it. This phase preserves that deletion policy; a missing
parent from legacy/administrative deletion fails closed, tested independently.

Example durable payload (digests abbreviated for readability; actual values
are 64 lowercase hexadecimal characters):

```
{"snapshot_id":"<sha256>","profile_digest":"<sha256>","engine_version":"scoring-engine-v1"}
```

Durable success result:

```
{"snapshot_id":"<sha256>","profile_digest":"<sha256>","engine_version":"scoring-engine-v1","result_count":1}
```

Customer GET includes `job_id`, `status`, `complete`, `engine_version`,
`profile_digest`, `snapshot_id`, `candidate_count`, `source_state`, `result_count`,
`limit`, `offset`, and `items`. Each item has source_id, external_id and scoring
fields; there are no lease proofs, global listings or raw tender batches.

## Persistence and migrations

Migration 11 (`scoring.sql`) adds:

* scoring_public_revisions: hash PK, public source/external IDs, normalized
  public JSON and connector provenance.
* scoring_snapshots: hash PK, authorized account/org/company FKs, profile digest,
  engine version, bounded configuration/source counts and candidate count.
* scoring_candidates: snapshot/ordinal PK, unique snapshot/revision, FK to the
  public revision. No tender bodies in private candidate rows.
* scoring_results: job/source/external PK, unique job/ordinal, snapshot FK,
  score, completeness, bounded scoring JSON and calculated timestamp.

Scoped snapshot and bounded result-order indexes support reads. Snapshot scope
and exact job-scope filtering isolate results; private results never enter
source_opportunities. The fixed SQLite→PostgreSQL importer now includes these
tables in FK order, tolerates pre-11 legacy sources, and rejects missing scoring
tables when migration 11 claims to exist. SQL compiles with the existing adapter
for PostgreSQL; no live PostgreSQL server was used.

Migration 10 checksum remains
`95f679368a7c292f931d8b84e44ca3dec9a1c2970223f11b202337340962298b`.
Migration 11 checksum:
`b4a93fcf29d7ef1a7a241e79599cb123fdcb40eed54f32e00ed46add4694547c`.
Earlier schema files are immutable and were not edited. Existing tests referring
to the final migration as version 10 now address migration 10 explicitly.

## Retry, fencing and publication

Registered handlers are ordinary trusted code. Worker ExecutionContext receives
a fenced_write capability enclosing its current private lease proof. The narrow
JobRepository.fenced_write extension locks/checks the job lease, executes a
bounded application write transaction, checks authoritative time again, and
rolls back if the lease expired. Job payloads cannot choose or import callbacks.
No lease proof is stored in results or exposed by HTTP.

All scores are materialized in one transactional, deterministic upsert batch.
A partial write crash rolls back. A crash after materialization but before job
completion leaves rows invisible; a valid retry upserts the same identities.
Only the existing lease-fenced complete() publishes success. GET verifies the
materialized count agrees with the safe completed job result. Expired/replayed
workers cannot write or complete. This is at-least-once execution with idempotent
materialization, not distributed exactly-once execution.

Retryable: storage unavailability/transient relational read/write errors, lease
loss or expiry (queue recovery/backoff applies). Permanent: missing/deactivated
account/member/company, invalid profile, changed profile identity, invalid
payload/snapshot/configuration, invalid normalized public revision, invalid
scoring model, integrity/programming schema errors. Persisted errors use only
existing safe queue failure codes, never exception strings. Unexpected handler
errors retain the existing sanitized handler_error policy. Redis is unnecessary
for correctness; there are no quotas or new observability subsystems.

## Workers and operations

```
python -m app.jobs.worker --scoring
python -m app.jobs.worker --rag
python -m app.jobs.worker --connectors
python -m app.jobs.worker --rag --connectors --scoring
```

Any distinct combination of those approved flags works. No flags, duplicates or
unknown flags safely refuse startup. Handlers are explicitly registered; there
are no dynamic imports from payloads, eval/exec, or web auto-started workers.
Scoring-only mode does not construct connector transports or RAG providers.

Operator prerequisites: migrate the shared database through 11, run the API and
explicit worker against that same database, retain active company profiles and
authorized memberships, and populate desired public sources separately through
connector workers. Existing job settings bound worker count, leases, retries and
shutdown. PostgreSQL SQL generation/import are verified offline only; production
concurrency, provider credentials, actual source coverage and live end-to-end
integration still require separately authorized verification. Historical public
revisions/private snapshots have no retention cleanup in this phase; operators
must account for retained data/storage. No dependency, deployment, production
change, commit or push was made. Phase 24S.1I is next and remains unimplemented.

## Offline validation

`tests/test_scoring_workers.py` exercises real SQLite, queue, handler, restart and
authorized API paths. External DNS/connections are explicitly blocked; only
Windows asyncio's local loopback socketpair is allowed. Tests cover golden
metadata values, parity, explanations/currencies/exclusions/missing metadata,
ordering/pages/empty snapshots/bounded history, changed inputs/idempotency,
private scope and account/company switching, revoked/deactivated/missing
parents, CSRF/auth/roles, invalid payloads, partial rollback, post-write crash
replay, lease expiry/stale completion, safe wire contracts, importer/schema and
approved CLI combinations. Original and extracted formula ASTs were compared
against starting HEAD and are identical except the function name.

Focused regression additionally covers scoring/relevance, Discover, connector
workers, durable jobs, organization/security/API, database/migrations/import,
RAG ingestion, shortlist and search history. Full-suite and live integration
verification are deliberately excluded; the established Monitoring matcher
failure remains deferred to 24S.2. Final counts/check exits are recorded in the
completion report.

Final focused validation: **404 passed, 1 skipped**, exit 0. Of those,
**41 new scoring-worker tests passed**. The skipped check is the existing RAG
symlink test (Windows symlink privilege unavailable). No full suite was run. compileall (app, tests,
scripts) and git diff --check both exited 0. The existing Starlette/httpx
deprecation warning was not addressed and no dependency was added.

Exact focused modules:

```
tests/test_scoring_workers.py
tests/test_scoring.py
tests/test_discovery_preview_scoring.py
tests/test_keyword_boundaries.py
tests/test_currency_normalization.py
tests/test_organization_workflows.py
tests/test_discovery_full_ai_contract.py
tests/test_connector_workers.py
tests/test_jobs.py
tests/test_organizations.py
tests/test_organization_api.py
tests/test_organization_companies.py
tests/test_organization_data.py
tests/test_organization_pdf_rag.py
tests/test_postgresql_foundation.py
tests/test_database.py
tests/test_rag_ingestion.py
tests/test_api.py
tests/test_phase17_security_hardening.py
tests/test_session_access.py
tests/test_shortlist_api_behavior.py
tests/test_discovery_history_api_behavior.py
```

Validation used the project's existing sibling `tender-ai/.venv/Scripts/python.exe`
with VALYQON_EMAIL_MODE=disabled and VALYQON_AI_FALLBACK_ENABLED=false.
Branch remains phase24-professional-saas-core, HEAD remains
86ec71d8ebd1f4a851b2bd2b723b050bdf2f855b. All changes are uncommitted.
