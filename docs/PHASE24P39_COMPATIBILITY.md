# 24P.3.9 compatibility, migration readiness and evidence gates

Status: **PARTIAL**. Supported SQLite compatibility gates are implemented and
verified; the full P3 rollout gate stays closed. P24.2 real-browser acceptance
remains PENDING; published TED/CPV P3.3 integration remains PARTIAL. No P24.4/5/6
work was started. All fixtures are controlled offline data, not customer history.

## Roadmap and independently verified P3.8 baseline

The exact roadmap checkpoint is **Compatibility, justified migrations and rollout
gate**: migration decision before schema edits, preserve old D/H/S/P/R contracts,
upgrade old fixture DB, verify optional fields on new records, distinguish
capability/error states, require verified-data positive paths before P3 completes.
It does not mandate a migration, warehouse, full-analysis product extension or
historical backfill. The user's broader security checks are evidence gates within
this scope. Unsupported capabilities cannot substitute for completion.

Read the complete P3 enrichment register and P35/P36/P37/P38 documents; inspected
actual API/auth/storage/schema/bootstrap/tests. Earlier chronological planned or
not-begun statements are superseded only by later explicit checkpoint evidence.

```powershell
python .cache/phase24p3/run_tests.py p39-p38-baseline tests/test_analytics_api.py tests/test_analytics_service.py tests/test_company_history_paging.py
```

Before P3.9 edits: **118 passed, 0 skipped, 0 deselected, exit 0, 119.20s**,
one existing Starlette warning. Includes all 50 P3.8 API cases. The previous pasted
CODEX_EXIT marker alone was not accepted as proof. P3.8 remains **PARTIAL**:
authenticated H/replay works, but resource checks originally ran after SQL/body
materialization; D/R/P, PostgreSQL and consumer/browser acceptance are incomplete.

## Tested versioned compatibility matrix

| Contract / versions | Legacy guarantee and new boundary | Evidence suites |
| --- | --- | --- |
| D / original API v1 Discover | Existing identity/metadata/scoring/full-AI fields and repeatability retained; enrichment/provenance optional None. Default preview stage is not stored proof. No H-to-D promotion or fresh Discover POST for replay. | normalization, preview, full-AI, workflows, TED evidence |
| H / schema_meta 1 raw discovery response JSON | Raw event bytes, source lists, counters, writer and timestamps preserved. Original list defaults 50, clamps 100. P35 additive history page/snapshots retain fence, `[start,end)`, page 1..20; analytics page 1..100. New read_limits is opt-in, old calls unchanged. | history repository/API/paging; upgrade/size gates |
| S / raw Saved item JSON | Existing shortlist GET/POST/DELETE, company/tenant scope and viewer mutation restriction retained. Client metadata is not trusted source evidence. Optional sidecars round-trip; no S/H identity join. | shortlist contract/behavior/integration/repository; normalization; upgrade |
| R / scoring-engine-v1 wrapper and revisions | Account/org/company/current-digest checks; 500 candidates; original detail limit 50, allowed 1..100. P35 run-page manifest cap 1000; snapshot/ordinal/revision binding. R analytics unavailable; no identity-only join to D/H/P. | scoring workers, paging, ledger-11 revision preservation |
| P / tenders analysis_json, scoring_json, PDF hash | Old analyses/scoring readable; organization history is not company-bound proof. No invented company/profile/document binding; P analytics unavailable, no speculative columns. | PDF, company PDF, organization PDF/RAG, full-AI; upgrade P decode |
| O / source notice JSON and connector revisions | Old JSON without enrichment remains readable without rewrite. Identity/equality/source values unchanged. Existing connector-sync-v1 source/adapter-rN provenance and CSV/HTTP request paths preserved. | normalization O round-trip; all ten adapter suites; connector/framework/HTTP |
| NoticeEnrichment schema 1 / notice-enrichment-v1 | Optional absence stays None; identity and canonical evidence recomputation enforced. Unknown schema/normalizer/taxonomy versions fail validation, not reinterpreted. Raw bytes remain stored. Unknown date policies are preserved but unavailable to date consumers. | normalization, dates, mixed-policy gate |
| Preview metadata-preview-v2 / preliminary-fit-v1 | Finite numeric 0..90; Low `[0,35)`, Medium `[35,65)`, High `[65,90]`; Matched >=35 and High Fit >=65 unchanged. Full scoring stays separate 0..100. Missing/default stage, digest, malformed/conflicting scope/engine/policy is unknown. Explicit old preview can be historical only. | fit boundary/trust/digest tests; mixed-version API |
| Country iso3166-location-v1 | Explicit procurement location only; no currency/source/buyer/region inference. Multi-country memberships non-additive; filters/KPI/replay agree. | normalization/service; SAM fixture API replay |
| Classification observed-source-categories-v1 / source-classifications-cpv2008-v2 | Old outputs validated under old policy; AusTender/ZA remain independent. CPV 2008 exact strings/verified hierarchy edges retained, withheld edges explicit. No CPV-NACE or check-digit inference. | normalization, CPV registry/hierarchy, mixed-policy API |
| TED v3 aggregate CPV / separate eForms XML sidecar | Search arrays do not prove procedure/lot/part roles. XML context/roles/version remain separate and unwired to notice enrichment. Different lot classifications never flattened; SDK example never labeled published data. | TED evidence, eForms multi-lot/part/old-version rejection |
| Dates source-date-v1 / deadline-window-v1 | Legacy raw dates are not reparsed as new proof. Search persistence, publication/release/update, parser observation, preview time and R materialization remain distinct. UTC half-open bounds, separate calendar-only precision, explicit no-ZoneInfo unavailability. | dates/DST/timezone, paging microseconds, API predicates |
| Analytics company-analytics-v1 / observed-search-analytics-v1 | Additive H-only aggregate/rows/replay allowlist with signed scope/query/profile/version commitments. No old endpoint replaced; no lifetime totals, invented history, FX sums, current rescoring or side effects. | API/service and release-gate suite |

Original endpoints preserved: `/`, `/login`, protected `/dashboard`,
`/api/v1/auth/*`, organization/company/role routes, organization
`/discover/tenders`, `/discovery/history`, `/discovery/history/{id}`,
`/shortlist`, existing PDF routes and company `/scoring/runs/{job}`.
The additive analytics prefix is
`/api/v1/organizations/{org}/companies/{company}/analytics/v1`, serving
`/history/aggregate`, `/history/rows`, `/history/replay`, `/capabilities/D|R|P`.

## Six KPI provenance and population agreement

U is the authorized H union selected newest event/time/ID then ordinal, excluding
conflicting identities. Row filters select within U; row-dependent aggregates
recompute on that selected U. Replay repeats the signed fence/query/versions,
profile digest, deadline AsOf and complete stored-event-byte fingerprint.

| KPI | Provenance / unit / unknown semantics |
| --- | --- |
| Discovered | Unique supported `(source,external_id)` in selected U; verified successful empty U is zero; incomplete/failed sources produce null with observed numerator. |
| Matched | Eligible historical preview >=35, exact shared classifier/eligible denominator; unknowns separately counted. |
| High Fit | Eligible historical preview >=65, same policy/denominator; no full-AI or win probability substitution. |
| Active Sources | Distinct successful sources in selected SEARCH EVENTS, denominator attempted sources; successful empty observations count. Row filters do not rewrite event history. Unit is sources. |
| Countries | Distinct explicit supported tender countries; selected U denominator, unresolved evidence and overlapping membership disclosed. Unit is countries. |
| Closing Soon | Valid UTC deadline instants in `[as_of,as_of+W elapsed days)` over selected U. Date-only calendar selection separately labeled; missing/ambiguous/unsupported excluded. |

KPI drilldown rows are its tender identities, so cardinality KPI values need not
equal tender row counts. Top order is an explicit eligible-preview subset.
API/service tests enumerate expected sets and reconcile rows/aggregates/drilldowns
and stable population IDs across pages. Actual existing SAM/AusTender fixtures
also traverse parsers, Discover serialization, authorized H API and exact replay:
SAM US and AusTender category remain separate; no synthetic geographic inference.

## Migration decision and rollback readiness

**No P3.9 relational migration required or added.** Legacy schema_meta is 1.
Existing ledger versions 1..13 are auth, organizations, companies, tenders,
monitoring, rag, support, operations, jobs, opportunities, scoring, quotas,
synchronous_usage. Checksums include immutable `24S1A-v1` identity. Unknown
legacy versions or changed/unknown ledger identities fail atomically.
Existing optional notice/snapshot JSON and scoring_public_revisions are sufficient.
P company binding is unavailable rather than backfilled. No schema/checksum edits,
warehouse, new columns, destructive rewrite or inferred historical data.

Disposable SQLite release gates prove fresh full bootstrap/idempotency;
unledgered schema_meta=1 and genuine ledger-through-11 fixture upgrades through
the existing migration path; exact raw H/S/P/R revision preservation; old D/S
decode with absent sidecars/default stage not promoted; old P repository decode;
new enrichment/provenance round-trip on upgraded H; unknown-version/checksum
failure without mutation. Existing PostgreSQL SQL compiler/FK ordering is inspected
and tested with mocks, not a server.

SQLite EXPLAIN QUERY PLAN uses existing idx_discovery_search_history_scope for
scoped fenced/keyset ordering without a temporary ORDER BY B-tree. No evidenced
index gap justified migration. This is a plan assertion, not a performance or
PostgreSQL proof. All fixture upgrades use newly allocated `.cache/phase24p3`
databases. No production/user DB access or migration occurred. No real migration
is proposed/awaiting approval; future real-data migration requires explicit
approval and isolated backup/upgrade/rollback evidence. Established bootstrap
auth/company backfill is separate from analytics and never runs on analytics GET.

Rollback needs no down migration/JSON conversion. Remove only P3.9 opt-in call
spans/module; do not replace whole files containing earlier uncommitted work.
Disabling the additive analytics router is the safe fallback for unresolved gates;
old Discover/Saved/PDF/source routes are independent. No rollback was executed.

## Security, races, errors and resources

Session touch=False, current org membership and explicit company precede storage
and signing. Every page reauthorizes; final session/membership/profile check
precedes response. Viewer reads allowed, mutation rights unchanged. Tokens bind
account/org/company/query/page/order/timezone/window/policies/profile, expire in
one hour and invalidate on signing rotation, changed profile/version, logout or
revocation. API key alone is not a session. Stored source errors and future
credential-like extras are absent from allowlisted response and decoded token.

Same-fence two-pass verification plus independent final fingerprint includes all
event fields. Later backdated insert above max-ID fence is excluded;
deletion/body/source-list/timestamp/profile changes return 409. Changes after final
check are detected on next replay; reverted-between-checks mutations and recovery
of deleted bytes remain unsupported. This is not durable immutable retention.

New optional AnalyticsReadLimits only affects analytics H:

* SQLite query_only connection prevents writes. Progress handler cancels actual
  SQL VM execution at 1000-opcode checkpoints against request deadline; busy
  timeout is set to remaining budget at guard entry.
* Same-transaction scalar preflight selects at most 501 matching events and
  rejects >500 events, >16 MiB cumulative snapshot/source-report bytes or >8 MiB
  one snapshot BEFORE Python body deserialization. BLOB length counts UTF-8 bytes
  including NUL. Cumulative/multibyte/source-report caps are tested.
* Existing 5,000 row occurrences/union rows, 2 MiB envelope, page 1..100,
  51 batches/load (102/request) and cooperative 10-second budget retained.
* Additional snapshot JSON depth <=64 and value nodes <=100,000. Invalid syntax,
  duplicate keys, nonfinite and deep JSON yield redacted 503. Invalid row identity
  remains explicit partial coverage, not a silently verified zero.
* Shared cursor/date parsing now converts excessive JSON recursion and UTC
  boundary overflow to CursorError, giving 422 on the API. Deep unsigned tokens
  and year-1/year-9999 offset crossings are regression-tested; no signed payload
  format, expiration, scope or timestamp normalization is changed.
* Non-SQLite bounded analytics reads now fail closed with 503 until backend
  runtime proof. Legacy PostgreSQL calls omit the optional guard and are unchanged.

Remaining resource limitation: SQLite connection/I/O acquisition, JSON parsing/
object expansion, hashing, Pydantic/pure calculations and final authorization
are not preemptively cancelled. No hard whole-request wall-clock/peak-RSS/load or
concurrency-performance acceptance is claimed. Therefore the SQLite improvements
do not justify marking P3.8 or full P3.9 COMPLETE.

| State | Observable contract |
| --- | --- |
| Pending/unsupported origin | Authorized D/R/P capability: unavailable + precise reason. Industry/crosswalk/context acquisition unsupported. |
| Missing/invalid evidence | Typed normalization/date/fit reasons and unknown/exclusion counters; old/future evidence never promoted. |
| Partial coverage | Null KPI total + observed numerator and explicit source/storage coverage/reason; successful zero distinct from failure. |
| Auth / forbidden / absent authorized company | 401 / 403 / 404; never successful empty aggregate. |
| Drift / stale commitment | 409 reload; no GET repair or re-score. |
| Invalid/tampered/expired/rebound/repeated/unsupported controls | 422. |
| Corrupt/unavailable storage, exceeded limit, unverified backend | Redacted 503, not a successful unavailable/zero substitute. |

API tests compare all DB table rows before/after reads and forbid source/scoring/job
work. No history/Saved/PDF/score/session-touch writes occur on analytics GET.

## Verification and remaining blockers

P3.9 code changes are limited to new app/database/analytics_read.py, optional
repository page guard, API preflight/JSON complexity checks, and shared paging
exception handling. New tests live in tests/test_analytics_compatibility.py.
P38 documentation only gains a continuation link; progress only gains P3.9
status/evidence. Source adapters, scoring thresholds/engine, original schemas,
UI assets and prior tests are not changed by this checkpoint. Earlier uncommitted
and untracked work is retained; no git reset/clean/checkout or .tmp-phase24 access.
The ignored local runner/check artifacts remain in .cache/phase24p3.

Required runner `.cache/phase24p3/run_tests.py` preserves dotenv/connect guards;
added audit guards cover connect_ex, UDP sendto and outbound DNS before OS dispatch.
Tests prove rejections and emit synthetic dotenv audit events without opening a
secret. Loopback fixture services remain allowed. Node suites use local scripts
and current dashboard_html rendering; they do not constitute browser acceptance.
Counts/commands for completed final verification are appended below.

No postgres/psql command was found in runtime inventory. No user DB/connection
URL/environment secrets were inspected. PostgreSQL foundation/harness tests are
mock/SQL/SQLite checks, never claimed as PostgreSQL server acceptance.

Remaining blockers: P3.5 durable retention/run-manifest/UI paging limits;
published TED procedure/lot/part binding and supported industry crosswalk;
D/R/P analytics positive paths; disposable real PostgreSQL runtime verification;
hard whole-request resource/concurrency proof; P24.2 real-browser and future
consumer acceptance. **Do not open the full P24.4 charts rollout gate yet.**
The verified H subset is reviewable; fallback states cannot complete P3.
P24.4/5/6 remain unstarted. No secrets/network/installs/Docker/production,
staging/commit/push/deploy or preexisting `.tmp-phase24*` changes.

PRODUCTION_TOUCHED=False

## Reproducible final selections and intermediate evidence

Final focused selection:

```powershell
python .cache/phase24p3/run_tests.py p39-final-all-gates tests/test_analytics_compatibility.py tests/test_analytics_api.py tests/test_analytics_service.py tests/test_company_history_paging.py tests/test_analytics_fit.py tests/test_analytics_dates.py tests/test_analytics_normalization.py tests/test_discovery_history_api_behavior.py tests/test_discovery_history_repository.py
```

Final broad selection (57 explicit files, no secret-dependent exclusions or -k):

```powershell
python .cache/phase24p3/run_tests.py p39-broad-final tests/test_analytics_compatibility.py tests/test_analytics_api.py tests/test_analytics_service.py tests/test_company_history_paging.py tests/test_analytics_fit.py tests/test_analytics_dates.py tests/test_analytics_normalization.py tests/test_cpv_registry.py tests/test_cpv_hierarchy.py tests/test_eforms_xml.py tests/test_ted_api_evidence.py tests/test_discovery_history_repository.py tests/test_discovery_history_api_behavior.py tests/test_discovery_history_api_contract.py tests/test_discovery_preview_scoring.py tests/test_discovery_full_ai_contract.py tests/test_shortlist_api_behavior.py tests/test_shortlist_api_contract.py tests/test_shortlist_integration.py tests/test_shortlist_repository.py tests/test_saved_ui_contract.py tests/test_scoring.py tests/test_scoring_workers.py tests/test_web_auth.py tests/test_auth_api.py tests/test_session_access.py tests/test_auth_owner_link_migration.py tests/test_organization_api.py tests/test_organization_data.py tests/test_organization_companies.py tests/test_organization_workflows.py tests/test_organization_pdf_rag.py tests/test_pdf.py tests/test_company_profile_pdf.py tests/test_saas_core.py tests/test_premium_ui.py tests/test_phase24r_ui_audit.py tests/test_monitoring_ui_contract.py tests/test_responsive_ui.py tests/test_source_framework.py tests/test_source_catalog.py tests/test_source_http.py tests/test_source_http_cleanup.py tests/test_source_http_transport.py tests/test_austender_source.py tests/test_sam_gov_source.py tests/test_uk_fts_source.py tests/test_za_etenders_source.py tests/test_canada_buys_source.py tests/test_nz_gets_source.py tests/test_connector_workers.py tests/test_india_cppp_source.py tests/test_kz_goszakup_source.py tests/test_eis_business_metadata.py tests/test_ted_source.py tests/test_postgresql_foundation.py tests/test_postgresql_phase24s2b3_harness.py
```

Intermediate overlapping runs, all successful unless explicitly identified:

| Run | Evidence / sequence boundary |
| --- | --- |
| p39-gates-first | 5 failed, 14 passed; initial new fixture errors (Row vs tuple, mock-clock consumption, wrong policy field) and newly exposed absent deep-JSON API bound. Existing assertions untouched. |
| p39-migration-debug | 1 failed, 15 deselected, exit 1; same new Row-vs-tuple fixture comparison, then corrected. |
| p39-gates-corrected | 137 passed, exit 0, 148.76s; first 19 gates + API/service/paging, before added source/credential/runner gates. |
| p39-final-focused | 312 passed, exit 0, 173.29s; 9 files, then-current 21 new gates; before last actual-source and token-boundary additions. |
| p39-broad | 1463 passed, 2 skipped, 390 subtests passed, 0 deselected, exit 0, 385.41s; 57 files, before the last source test and cursor overflow/recursion handling. |
| p39-source-final | 1 passed, 21 deselected, exit 0, 5.83s; actual existing source-fixture API/replay gate. |
| p39-release-suite-final | 22 passed, 0 skipped/deselected, exit 0, 23.93s; before last token-boundary test. |
| p39-token-final | 1 passed, 22 deselected, exit 0, 5.01s; after final shared cursor/date exception fix. |

Final full selections rerun after the cursor/date handling change; their measured
results are recorded in the closure below. Intermediate counts overlap. No full
repository, real-source, PostgreSQL server or browser run is claimed.

Final guarded focused `p39-final-all-gates`: **314 passed**, exit **0**,
**178.57s**, 9 files, 0 skips/deselections. It includes all 23 release cases and
final application code. Guard-only hardening subsequently extended the same
runner check to forward/reverse legacy DNS calls and Windows case/trailing-dot/
space/ADS dotenv aliases; `p39-release-guard-final` then passed **23 cases**, exit
0, **32.46s**, no skips/deselections. This uses synthetic audit events, never a
secret file open. The final broad process started before that last guard-only
extension; all application changes and test case counts were already final.

## Closure evidence and checkpoint decision

Final broad `p39-broad-final`: **1465 passed, 2 skipped, 390 subtests passed,
0 deselected, exit 0, 377.30s**, 57 files. The only skips are existing raw-deflate
checksum cases at tests/test_source_http.py:805 and :1000 (raw deflate has no
checksum). One existing Starlette deprecation warning; no other failing,
silently skipped or excluded tests. Focused 314 and standalone release 23 counts
overlap this run and must not be summed. The final runner alias/DNS extension
is separately covered by all 23 release cases, as noted above.

Six current-render local JS suites passed individually, each exit 0: company,
discovery, discovery_full_ai, phase24r, premium, shortlist_ui. Existing Node
v24.21.0 used; current dashboard_html rendered into .cache/phase24p3/p39-dashboard.html.
Python compileall of app/tests/scripts and git diff --check passed. All 44
untracked files under app/scripts/tests/docs were additionally checked: Python
AST, JSON decoding, text conflict markers/whitespace and a path/size/SHA256
manifest in .cache/phase24p3/p39-untracked-manifest.json. The one original copied
SDK XML comment trailing-space line was preserved for exact byte fidelity,
not repaired or hidden. No .tmp-phase24 file was opened by these checks.

**P3.9 PARTIAL**, supported SQLite compatibility/evidence subset delivered.
**P3.8 PARTIAL**, SQL/body subset improved but whole-request resource and
unavailable-origin/runtime gates unresolved. Overall P3 is not COMPLETE.
**P24.2 browser PENDING; published P3.3 PARTIAL; P24.4/5/6 NOT STARTED.**
Migration decision: no new migration; readiness: withhold full P24.4 rollout.
