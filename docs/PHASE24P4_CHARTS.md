# Phase 24P.4 charts prerequisite review (2026-10-11)

## P3.9C independent execution: P4 remains BLOCKED

The current Windows synthetic process tests independently passed (25 passed,
0 failed/skipped, exit 0). This is an UNWIRED SYNTHETIC PROTOTYPE; actual analytics,
authentication, PostgreSQL and live-server requests have not been isolated.
Committed-memory and initialized-child timeout/kill/reap evidence do not prove
CPU/RSS, startup or whole-request limits. P3.9 stays PARTIAL. P4 remains BLOCKED
pending explicitly accepted prerequisites and rollout policy; no P4/P5 work.
See [current independent evidence and next checkpoint](PHASE24P39_RUNTIME_GATE.md).


## P3.9B prototype: P4 remains BLOCKED

Windows-only synthetic process isolation proof is independent of all API/UI paths.
Job kill/reap and committed-memory allocation limit do not close CPU/RSS,
startup/auth/acquisition, live-disconnect, PostgreSQL or browser prerequisites.
P3.9 remains PARTIAL; no chart/P5/widget implementation or rollout authorization.
See [runtime gate](PHASE24P39_RUNTIME_GATE.md) for current precise evidence.


## P3.9A continuation: gate remains BLOCKED

LIMITED H admission now bounds two operations per app (normally per process),
rejects overload with 503/Retry-After: 1 and retains cancelled awaiters' slots
until actual worker completion. Dedicated workers perform JSON/aggregate/output;
orderly shutdown joins before owned runtime close. This addresses admission and
worker ownership, not hard CPU/RSS, stuck-thread termination, global concurrency,
actual PostgreSQL, retention or browser/consumer gates. No chart/P5/widget or
UI binding was added. P3.8/P3.9 PARTIAL; P4 BLOCKED. Dev-only SQLite H rollout
requires separate explicit authorization. The latest
[runtime gate](PHASE24P39_RUNTIME_GATE.md) supersedes older runtime-gap statements
below; historical test reports remain intact.

P3.9A measured verification: focused 335 passed; final admission 13 passed;
broad 1489 passed, 2 existing raw-deflate skips, 390 subtests passed, exit 0,
481.93s. Six local JS suites, compileall, diff-check and untracked inspection
passed. These are offline backend/logic results, not browser/consumer acceptance.
Next backend step: hard process/OS isolation including termination/reap and
auth/acquisition coverage. P4 remains BLOCKED pending accepted prerequisite and
separately authorized rollout policy; no P5 workaround.



Status: **BLOCKED; chart implementation not started.** This follows the user's
explicit instruction to mark P4 BLOCKED when a critical backend prerequisite is
incomplete, and the actual P3.9 rollout decision. No application code, prior tests,
scoring, source adapters, population service or existing UI was modified here.

### Runtime prerequisite continuation

The later focused backend review is recorded in
[PHASE24P39_RUNTIME_GATE.md](PHASE24P39_RUNTIME_GATE.md). It adds pre-expansion
JSON complexity and early query-byte guards, but does not close admission,
event-loop CPU, whole-request memory/preemption or disconnect-worker gaps.
Recommendation **(b): further backend checkpoint**. P3.8/P3.9 remain PARTIAL;
development-only SQLite H charts are not enabled or authorized. P4 stays BLOCKED
until an explicit accepted policy/gate decision after the documented evidence.
P2 browser acceptance and future consumer acceptance remain pending.
Current backend continuation broad result: 1476 passed, 2 existing raw-deflate
skips, 390 subtests passed, exit 0; six existing JS suites passed. These results
do not close runtime/consumer/browser gates or implement any chart.

## Baseline and gate decision

Reviewed PHASE24_PROGRESS.md's P1 evidence, P2 implementation/acceptance notes,
exact P4 roadmap/dependencies, P37/P38/P39 documents, actual command-center HTML,
premium CSS/JS, shell context invalidation, analytics routes/public schemas,
SQLite read limits, API/service/compatibility tests and existing UI tests.

P4 explicitly depends on P2 and P3. The latest P39 closure says:
**"Do not open the full P24.4 charts rollout gate yet."** P38 and P39 remain
PARTIAL; passing their supported-subset tests does not remove that gate.

The code corroborates the critical resource/runtime gap. `bounded_read` rejects
non-SQLite connections before SQL with StorageError (API 503). SQLite's progress
handler, query-only connection and pre-body byte/event limits protect the SQL/body
subset. Connection acquisition, JSON object expansion, hashing, pure calculations
and final authorization still lack preemptive whole-request time/memory bounds.
HTTP abort alone would not cancel all underlying threaded work. No disposable
PostgreSQL runtime proof or hard whole-request/concurrency proof exists here.
Providing those guarantees requires backend design/runtime acceptance beyond a
narrow chart prerequisite fix under this checkpoint's offline constraints.

Other retained P39 issues: no durable immutable retention/lost-byte recovery,
D/R/P positive analytics paths unavailable, published TED XML context integration
PARTIAL, industry crosswalk unsupported. These are not silently promoted to
completed requirements. The observed H subset can be useful, but it is not the
completed P3 rollout prerequisite. No newly confirmed narrow defect justified
changing the backend during this review.

## Before/after UI contract and supported future bindings

Before and after this checkpoint, all six premium KPI slots and chart panels
remain unavailable; there are **no new UI-to-API bindings, chart series, filters,
drilldown actions or cache**. Existing context loading/error/no-company handling
and navigation are preserved. Existing session-discovery counters remain separate.
Some P2 placeholder copy predates the implemented P3 policies; retaining it is
not a claim that those backend policies are absent. Its correction belongs with
the gated consumer implementation and corresponding UI contract tests.

The following is an audited future binding map, **not implemented UI behavior**:

| UI | Existing public H API field / truthful semantics |
| --- | --- |
| Six KPI cards | `kpis[Discovered/Matched/High Fit/Active Sources/Countries/Closing Soon]`: preserve nullable value, observed numerator, denominator, unit, coverage and reason. |
| Company Fit | `distributions.fit_bands`; historical search-time preview, unknown separate, never current fit or winning probability. |
| Geography | `distributions.countries`; explicit country memberships over filtered U; multi-country totals non-additive. |
| Categories | `distributions.categories`; exact scheme/code, supported notice-level evidence, independent source taxonomies. |
| Sources | `distributions.sources`; tender identities distinct from event-level `source_observations` and Active Sources cardinality. |
| Search activity | `search_activity`; observed historical search-day identities, not publication or live market growth; no fabricated empty days/interpolation. |
| Publication/date distributions | `distributions.date_distributions`; retain semantic, precision and day, never merge release/update/search/publication. |
| Deadlines | `deadline_buckets`; distinguish instant and date-only kinds, explicit timezone and one server deadline as_of. Missing is not zero. |
| Industry | No supported crosswalk/public series; unavailable explanation required. |
| Advanced widgets | Top Opportunities, source-health/completeness widgets remain P5, not implemented here. |

The API envelope binds origin H, explicit organization/company, profile digest,
filters, versions, selected events, observation/retrieval times, coverage and
population ID. Signed population_token/cursor replay requires identical query,
page size and order; changing a KPI/filter while reusing that token is invalid.
No origin D/H/R/P joining by source/external identity is authorized. Public rows
contain event/ordinal/snapshot hash and eligible historical score, but deliberately
exclude arbitrary tender titles, URLs, bodies and raw source errors. Existing
Discover links are navigation only, not a reproduction of H. A future consumer
must display/replay authorized H rows from the same commitment without Discover
POST or GET rescoring and without substituting independently fetched history.

## Existing safeguards and outstanding consumer acceptance

Existing API authorizes session with touch=False, membership and addressed company
before history access and independently checks authorization/profile before
return. Every page reauthorizes; tokens bind account/scope/query/policies/profile,
expire and invalidate on logout/rotation/drift. Responses are no-store and
allowlisted. Errors stay distinct: 401/403/404, drift 409, invalid controls 422,
storage/resource/runtime 503. No source crawling/scoring/write on analytics GET.

No new chart XSS, SVG geometry, browser history, stale-fetch, scope revalidation,
CSRF/session integration or accessible table implementation was delivered or
claimed tested. Existing premium context JS uses textContent and clears KPI
presentation on context changes; its suite proves context state isolation only.
Future P4 must add safe text rendering, finite/clamped geometry, independently
verified scope/profile/filter/population commitments, abort plus epoch guards,
immediate invalidation, safe retries, keyboard/table alternatives and responsive
acceptance. Those future requirements cannot be marked passed by existing tests.

## Verification

Measured final commands/counts are appended below after process completion. All tests
use the existing guarded runner/local Node, controlled fixtures and new dedicated
cache directories. No full-repository, browser, production, live-source or real
PostgreSQL test is claimed. No browser was launched; P2 and P4 visual acceptance
remain **PENDING**. No new chart tests were added because no chart code was added.

## Practical follow-up

Resolve the P38/P39 whole-request resource/runtime gate in a separately authorized
backend checkpoint with deterministic cancellation/memory/concurrency evidence
and disposable backend acceptance. Explicitly settle rollout policy for the
SQLite-only H subset and retained retention limitations before reopening P4.
Then implement the mapped H consumer and its populated/partial/unknown/stale/XSS
tests, followed by actual browser inspection. P5 should follow accepted P4; do
not begin its advanced widgets or P6/production now.

PRODUCTION_TOUCHED=False

### Independently measured baseline

```powershell
python .cache/phase24p3/run_tests.py p4-baseline-20261011 tests/test_analytics_compatibility.py tests/test_analytics_api.py tests/test_analytics_service.py tests/test_company_history_paging.py tests/test_analytics_fit.py tests/test_analytics_dates.py tests/test_analytics_normalization.py tests/test_discovery_history_api_behavior.py tests/test_discovery_history_repository.py
```

Result: **314 passed, 0 skipped, 0 deselected**, exit **0**, **249.52s**,
one existing Starlette TestClient/httpx deprecation warning. This focused baseline
ran before any checkpoint edits and includes all 23 compatibility release cases.
It exercises all six API KPI values, unknown/partial evidence, memberships,
deadline precision/timezones, filters, paging/replay, real source fixtures,
authorization/revocation/logout/drift, redacted source errors and read-only guards.
It does not prove the outstanding whole-request/runtime/consumer gates. The
previous pasted ENV_UNCHANGED marker was not independently remeasured; no claim
about an environment snapshot comparison is made.

Six existing local JS suites passed individually, exit 0: company, discovery,
discovery_full_ai, phase24r, premium, shortlist_ui. Existing Node v24.21.0; actual
current dashboard_html rendered to `.cache/phase24p3/p4-dashboard.html`. These
custom DOM/VM suites are not a browser. No new chart suite exists.

`python .cache/phase24p3/p4_checks.py`: compileall app/tests/scripts passed;
git diff --check exit 0 (existing LF/CRLF notices only). Separate untracked
inspection covered **45 files** under app/tests/scripts/docs: Python AST,
JSON parsing, merge markers, whitespace and SHA256 manifest at
`.cache/phase24p3/p4-untracked-manifest.json`. One preexisting copied official SDK
XML comment's whitespace was preserved for byte fidelity, as in P39. No other
untracked errors were found. Existing .tmp-phase24 directories were excluded
without opening their files. The check helper is a new ignored copy of P39's
existing helper with separate output names; the original was not changed.

### Final broad verification and decision

Guarded run **p4-broad-20261011** repeated the exact **57 explicit test files**
in P39's documented `p39-broad-final` command, changing only the run directory.
The command was extracted from docs/PHASE24P39_COMPATIBILITY.md and passed as
arguments to the existing runner; no -k selection or excluded file was added.
Includes analytics/API/compatibility, auth/session/organizations, history,
Discover/full-AI, source adapters/HTTP/connectors, Saved, PDF, UI, CPV/XML and
mock PostgreSQL foundation/harness coverage.

Result: **1465 passed, 2 skipped, 390 subtests passed, 0 deselected**, exit **0**,
**492.82s**, one existing Starlette warning. Skips are exactly
tests/test_source_http.py:805 and :1000: raw deflate has no checksum.
The 314 focused cases overlap the broad selection and must not be summed.
Both selections use the current guarded runner, including its alias/DNS guards.
No test assertion was weakened and no new test/code defect was exposed.

**Verified P3.9 status remains PARTIAL; P4 BLOCKED.** Green supported-subset
regression is not whole-request resource, PostgreSQL server, chart consumer,
browser or production acceptance. No chart currently displays verified API data
in the premium dashboard; all six cards/panels remain unavailable. Available H
data is recorded above solely as a future binding map. P5 is recommended only
after reopening and completing P4, not as a workaround for the closed gate.


## P39D: executable local H fixture path; full P4 still BLOCKED

Existing aggregate_history() now actually runs in a short-lived Windows fixture
worker through NEW offline_fixture/offline_spike/offline_worker modules, without
changing existing API/UI code. New 43-case final suite passed; relevant ten-file regression 372 PASS (203.81s), exit 0, 0 SKIP.
Six KPI parity includes identities/denominators/unknown-zero/profile/timezone/
as_of/filter, and legacy/foreign/future current-fit refusal. Precise evidence,
startup gap and cap measurements are in the appended P39D runtime gate.
The premium KPI cards/charts remain unavailable; no chart/browser proof is claimed.
P3.9 PARTIAL; P4 full rollout BLOCKED. Synthetic P39B is not upgraded to real-H
isolation by this fixture-only development spike.

ONE next bounded checkpoint is a functioning LOCAL fixture H charts preview,
separate entry point disabled by default, explicit local opt-in and loopback-only
binding (reject 0.0.0.0/non-loopback). It can use disposable SQLite query-only
fixture storage; actual PostgreSQL is NOT a prerequisite for drafting this local
preview. Tests must prove default-off, non-loopback refusal, no live DB/network/
secrets/writes, correct six KPI/unknown/date/filter display and context invalidation.
Consume the pinned real-H output; never present fixture scope as membership or
production data. No existing analytics HTTP integration, production entry-point
or rollout; future authenticated integration requires parent final reauthorization
and independently accepted startup/resource/backend safety gates.
No P4 chart code was added in P39D. PRODUCTION_TOUCHED=False.


## P39E: working standalone local H fixture preview (2026-10-11)

P39E LOCAL DEMO implemented: explicit --build-fixture entrypoint generates one
self-contained file, seven real P39D Windows child calculations, six KPI cards,
historical fit-band and distinct typed deadline charts, accessible exact table,
identity drilldown and case invalidation. No HTTP service or live assets changed.
P3.9 PARTIAL; full P4 public rollout BLOCKED; P5 not enabled.

Observed baseline 103 PASS (15.81s); relevant 11-file regression 386 PASS
(121.03s, before final parent guard/test additions); final new suite 20 PASS
(3.76s), all exit 0, no skips. Six existing JS suites and new P39E Node
DOM/geometry/case suite passed. Successful explicit build and deterministic
42056-byte HTML verified; default-off preserves existing output. Browser
visual/CSP/file-origin acceptance PENDING: no browser launched. Details,
commands, exact path and limitations: [local preview](PHASE24P39_LOCAL_PREVIEW.md).

Existing tracked/untracked edits retained; .tmp-phase24* not opened/cleaned.
No DB, production, network, installation, commit/push/deploy or migration.
PRODUCTION_TOUCHED=False.
