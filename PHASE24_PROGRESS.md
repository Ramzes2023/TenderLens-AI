# Phase 24 Professional SaaS Core

### P3.9C measured relevant regression and local checks

Exact command, fresh basetemp:
```powershell
python .cache/phase24p3/run_tests.py p39c-regression tests/test_analytics_process_isolation.py tests/test_analytics_admission.py tests/test_analytics_runtime_gate.py tests/test_analytics_api.py tests/test_analytics_compatibility.py tests/test_analytics_service.py tests/test_company_history_paging.py tests/test_analytics_fit.py tests/test_analytics_dates.py
```
**329 passed, 0 failed, 0 skipped/deselected, exit 0, 195.44s** on Windows;
includes all 25 process cases. Counts overlap the initial run; do not sum them.
One existing Starlette/httpx deprecation warning; no test errors or sandbox blocker.
No broad 1489-test rerun; historical totals are not new execution evidence.
`python .cache/phase24p3/p39c_checks.py`: exit 0; all six local Node suites
(company, discovery, discovery_full_ai, phase24r, premium, shortlist_ui) exit 0;
compileall of process_isolation.py and its test passes; git diff --check exit 0.
Git emitted existing LF/CRLF conversion warnings. Fresh helper/output names preserve
previous cached artifacts. No dependency installation or browser/server execution.

## P24P.3.9C independent Windows execution and narrow audit (2026-10-11)

**P3.9 PARTIAL; P4 BLOCKED. P39B remains an UNWIRED SYNTHETIC PROTOTYPE.**
This checkpoint independently executed the existing tests BEFORE any code change.
HEAD 93f02eb, branch phase24-professional-saas-core; implementation/tests unchanged.
Platform: win32, Windows 11 10.0.26200-SP0, Python 3.12.14 AMD64.

`python .cache/phase24p3/run_tests.py p39c-process-initial tests/test_analytics_process_isolation.py`
returned **25 passed, 0 failed, 0 skipped, exit 0, 5.58s**. No test errors.
Fresh basetemp; no Windows skip or runner/security modification. These are actual
Popen children and kernel32 Job Objects, not code-authoring/runner-exit claims.
Some invalid-input/setup fault tests deliberately mock failures; they are not
substitutes for the real process, memory, timeout and job-close cases.

Verified: job creation/set/query/assignment, 64 MiB OS process committed-memory
limit (64 MiB + 4096 VirtualAlloc denied; same fixed control child succeeds and
frees allocation without page touches), parent wall-clock timeout of an initialized
30-second sleeping child, cancellation/shutdown, job-close termination, owned
handle wait/reap, active-child/task cleanup and five-job handle-count stability.
Crash/exception, malformed/overlong output, result/PID checks and slot reuse pass.
Active-process limit 1 is read back; descendant enforcement is NOT demonstrated.
No CPU quota, RSS/peak whole-request/parent-memory bound or hostile-code sandbox
is proved. No unrestricted resource exhaustion or unrelated process termination.

Narrow audit: ctypes HANDLE/signatures and memory flags are consistent with the
exercised paths. Assignment precedes request input, but interpreter startup is
NOT suspended and occurs before assignment. stdout is bounded; stderr goes to
DEVNULL. Retained Popen handles own termination/reap; five repetitions show no
handle leak on exercised paths. Start/assignment faults are exercised, but arbitrary
Win32 cleanup failures and all races are not exhaustively proved. Cleanup has no
await and retains task ownership if it fails; synchronous startup, stdin write and
up-to-five-second reap cannot be preempted by the polling deadline. No fix was
needed or assertion weakened. Forced real-server parent death remains untested.

Offline/network/DNS/dotenv guards stayed intact; subprocess/Job Object operations
were allowed without elevation or security bypass. No real analytics/authentication,
connection acquisition, PostgreSQL, live HTTP disconnect or browser isolation proof.
Existing work and .tmp-phase24* preserved; no staging/commit/push/deploy or rollout.
Historical P39B reports below are retained; current independent evidence is here.

ONE next checkpoint: a bounded backend integration design for ownership across
auth/acquisition/calculation and disposable-server acceptance criteria, explicitly
settling startup and committed-memory versus RSS/CPU policy before any API wiring.
P4 requires explicitly accepted prerequisites; no P4/P5 implementation here.
PRODUCTION_TOUCHED=False.


## Latest P24P.3.9B WINDOWS experimental isolated-process proof

**P3.9 PARTIAL; P4 BLOCKED; P5 not started.** Independent synthetic Windows-only
process prototype added, no API/runtime/admission/DB/chart integration. Actual
Job Object assignment, kill/wait/reap, cancellation/shutdown, two-child immediate
capacity, bounded JSON IPC, parent result/PID verification and 64 MiB committed
memory allocation refusal proved locally. CPU quota and RSS remain unsupported;
startup is not suspended/fully capped, parent/auth/acquisition remain outside.
See [precise evidence and limitations](docs/PHASE24P39_RUNTIME_GATE.md).
Previous 1489 passed + 2 skipped / 390 subtests is historical, preserved.
ONE next checkpoint: synthetic suspended-start/lifetime and CPU-cap acceptance,
with explicit committed-memory/RSS policy; keep API disconnected. No rollout,
P4/P5, production, network, installs, secrets, staging/commit/push/deploy.
PRODUCTION_TOUCHED=False.


P3.9B accepted offline results: new prototype **25 passed** (11.77s);
existing API/admission/compatibility/security/auth **142 passed** (216.82s);
remaining analytics/history **241 passed** (36.92s), all exit 0, no skips/deselections.
These three selections have zero shared test IDs; historical/rerun counts overlap
and must not be added. Prior broad 1489+2/390-subtests was not rerun. Six JS suites,
compileall, diff-check and 52-file untracked inspection passed. No live server,
PostgreSQL server or browser run. Exact commands are in the runtime gate.

## Latest P24P.3.9A LIMITED admission/cancellation checkpoint

**P3.8/P3.9 PARTIAL; P4 BLOCKED; P5 not started.** H GET now has lifespan-owned
immediate admission (two per app, normally per process), dedicated workers,
503/Retry-After: 1 overload, and slots retained after HTTP coroutine cancellation
until actual submitted worker exit. Large JSON/calculation/response serialization
moved off event loop; auth/final scope checks and worker join are included.
No hard CPU/RSS/forced shutdown, global cap, PostgreSQL server or browser proof.
Stuck threads can delay shutdown indefinitely. Previous work is preserved;
no P4 rollout accepted. See [runtime gate](docs/PHASE24P39_RUNTIME_GATE.md).
Measured guarded results: focused **335 passed** (234.14s); final admission
**13 passed** (33.44s); owned-lifespan check **1 passed, 12 deselected** (5.52s).
Broad exact documented 57 files + two runtime files: **1489 passed, 2 skipped,
390 subtests passed, 0 deselected**, exit **0**, **481.93s**. Both skips are existing
raw-deflate checksum cases at tests/test_source_http.py:805/:1000. Counts overlap.
Six local JS suites, compileall, diff-check and 50-file untracked inspection pass.
Earlier results below remain historical. Recommended next step: separately scoped
hard process/OS CPU/RSS isolation, termination/reap and auth/acquisition acceptance.
PRODUCTION_TOUCHED=False.


## Latest focused P24P.3.9 resource/runtime gate (2026-10-11)

**P3.8/P3.9 PARTIAL; P4 BLOCKED; P5 not started.**
See [docs/PHASE24P39_RUNTIME_GATE.md](docs/PHASE24P39_RUNTIME_GATE.md) for the
actual request/storage trace, proven ceilings, remaining architectural blocker
and narrow follow-up design. Added conservative cumulative JSON complexity/depth
validation before expansion and a 16 KiB raw history query ceiling before handler
authorization dispatch. Existing SQL/read-only/scope/replay protections retained.
Recommendation **(b): further backend checkpoint**, with bounded admission and
worker-lifetime cancellation evidence; process/OS isolation if hard CPU/memory
limits are mandatory. No development-only chart policy was silently accepted.
P2 visual-browser acceptance remains pending. No real DB/config/credentials,
network, Docker, installs, staging/commit/push/deploy or prior temporary work touched.
Measured current-run results are in the runtime-gate document below.

Current guarded results: focused **324 passed** (209.07s), standalone final new
cases **11 passed** (6.73s); broad **1476 passed, 2 skipped, 390 subtests passed,
0 deselected**, exit 0 (440.96s). Selections overlap; do not sum counts. Broad
uses previous 57 explicit files plus the new runtime-gate test file, no -k or
extra exclusions. Both skips are existing raw-deflate checksum cases at
tests/test_source_http.py:805/:1000. Six JS suites, compileall, diff-check and
separate inspection of 48 untracked app/tests/scripts/docs files passed.
One existing Starlette warning; no full-repository/server/browser proof claimed.

## Starting point

Started from verified clean branch:

- Branch: `phase23-global-sources-wave1`
- SHA: `ac6e69d7a94ded7e67b81a8ee5537619d27b0fa5`

Development branch:

- `phase24-professional-saas-core`

## Completed

- Professional public VALYQON AI landing page.
- Session-aware landing CTA.
- VALYQON AI branding:
  - Find. Analyze. Score. Win.
  - Global Procurement Intelligence powered by AI.
- Responsive authenticated SaaS application shell.
- Desktop sidebar and mobile navigation.
- Active organization and active company context.
- Existing Telegram, monitoring, company and team controls preserved.
- Professional Overview workspace.
- Global Discover workspace connected to the existing organization discovery API.
- Tender result cards using real discovery metadata.
- Client-side discovery filtering.
- Preliminary company fit score displayed truthfully.
- Data completeness displayed separately from fit score.
- Metadata preview clearly distinguished from full AI analysis.
- Partial source failure and total source failure UX.
- Repeatable discovery preserved without seen-state mutation.
- Tender metadata detail workspace.
- Scoring criteria and missing-information presentation.
- Honest placeholders for documents and full AI analysis.
- Safe official tender links.
- Stale request / workspace change protection using abort and epoch guards.
- Shared organization company creation and editing.
- Existing company profile constraints preserved during PATCH updates.
- Viewer mutation protection retained.
- Company form expanded using fields already supported by the existing profile model.
- First-run / no-company onboarding guidance.
- Create / activate company flow leads users toward discovery.
- Latest browser-session discovery counters on Overview.
- Loading, empty and error-state improvements.
- Public root `/` intentionally changed from login redirect to public landing page.
- Protected `/dashboard` still redirects anonymous users to `/login`.
- Existing authentication, organization and role boundaries preserved.

## In progress

24P.2 presentation implementation is delivered; required real-browser acceptance is blocked by unavailable browser tooling (see verified 24P.2 results below).

A real browser visual/mobile review is still recommended before claiming final visual readiness or deployment readiness.

## Not started

These remain deliberate future product phases rather than incomplete Phase 24 backend services:

- Saved opportunities service (original Phase 24 starting-point status; existing Saved functionality is now implemented as recorded in the read-only UI audit below)
- Recommended opportunities service
- Billing/payment integration
- Notification inbox
- Full source document acquisition
- Full discovered-tender AI analysis
- Email verification
- Shared entitlement/free-analysis ledger
- Advanced account security and recovery

No additional procurement sources were added in Phase 24.

## Files changed

Major Phase 24 files include:

- `app/api/landing.py`
  - Professional public landing page.

- `app/api/saas_shell.py`
  - Authenticated SaaS shell, navigation, workspace context and future states.

- `app/api/discovery_ui.py`
  - Discover workspace markup.

- `app/api/static/saas.css`
  - Responsive professional SaaS styling.

- `app/api/static/shell.js`
  - Workspace, organization, company and navigation behavior.

- `app/api/static/discovery.js`
  - Discovery rendering, filters, source status, tender details and stale-response protection.

- `app/api/dashboard.py`
  - Shared-company profile UX, create/edit flow and dashboard integration.

- `app/api/main.py`
  - Static asset mounting.

- `app/api/routes.py`
  - Public landing route integration.

- `app/api/schemas.py`
  - Discovery response metadata exposure.

- `app/api/organization_workflow_routes.py`
  - Existing discovery metadata surfaced to the SaaS workspace.

- `tests/test_saas_core.py`
  - SaaS shell, landing, assets and company regression coverage.

- `tests/js/discovery.test.cjs`
  - Discovery browser-logic regression.

- `tests/js/company.test.cjs`
  - Company profile preservation and viewer mutation regression.

- `tests/test_web_auth.py`
  - Updated public landing expectation while preserving protected dashboard behavior.

- `tests/test_organization_workflows.py`
  - Organization/company workflow regression coverage.

## Backend/API changes

- `GET /`
  - Now serves the public session-aware VALYQON landing page.
  - Returns `Cache-Control: no-store`.

- `/assets`
  - Serves local SaaS assets.

- Existing organization discovery API remains the source for Discover:
  - `POST /api/v1/organizations/{organization_id}/discover/tenders`

- Discovery response exposes existing tender metadata including optional publication date and summary.

No procurement adapter, scoring engine, authentication model, database architecture or production deployment configuration was replaced.

## Frontend changes

Implemented:

- public landing
- authenticated navigation shell
- Overview
- Discover
- tender cards
- tender detail workspace
- preliminary matching presentation
- company creation/editing
- onboarding
- source health/error states
- responsive CSS
- keyboard/focus accessibility improvements

Future sections remain visibly non-functional placeholders rather than simulated features.

Personal legacy companies remain distinct from shared organization companies.

Global Discover guides users toward a shared organization without silently moving personal data.

## Tests

Final Python regression:

- `399 passed`
- `3 skipped`
- `1 existing Starlette deprecation warning`
- `38 subtests passed`
- exit code `0`

Web authentication regression:

- `5 passed`
- exit code `0`

JavaScript regression:

- Company profile preservation and viewer mutation guard: PASS
- Discovery rendering, filtering, safe links, partial failures, repeatability and stale-response handling: PASS
- Company JS exit code: `0`
- Discovery JS exit code: `0`

Additional validation:

- Python `compileall`: PASS
- `git diff --check`: PASS

Browser visual smoke:

- Not completed.
- Codex Playwright browser executable was unavailable.
- No unsupported claim of visual/browser verification is made.

## Git commits

Completed checkpoints:

- `2cc6605` â€” Build professional VALYQON SaaS shell
- `f1a4958` â€” Add global tender discovery workspace

Final company/onboarding/polish checkpoint is represented by the current Phase 24 finalization commit.

## Known issues

- Real browser visual/mobile review remains pending.
- Existing Starlette TestClient/httpx deprecation warning remains; it does not fail the suite.
- Future product sections intentionally remain placeholders where corresponding backend services do not yet exist.

## Exact next step

The original checkpoint follow-up remains required visual validation work:

1. Perform a real browser visual review of landing, dashboard, Discover, tender detail and company onboarding on desktop and mobile widths.
2. Fix only genuine visual/usability defects found during that review.
3. Close visual readiness only after that review.

Phase 24P.0 is fully completed below; JavaScript runtime verification passed on 2026-10-10. This roadmap update does not authorize commit, push or deployment.

Do not deploy Phase 24 to production as part of this checkpoint.
Do not add procurement sources.
Do not resume the abandoned TED document experiment.

PRODUCTION_TOUCHED=False
## Premium UI/UX continuation

Starting SHA: 1ff95899cbb8ce4cefe314f5f277fab815b759ca. Verified clean branch.
Completed visual areas: redesigned split landing hero with labeled HTML example,
product workflow, coverage cards, intelligence/monitoring/team story and pricing teaser.
Auth retains its two-panel architecture, with shared navy/blue styling, back navigation,
password visibility control and generic error handling.
Current audited implementation: premium application shell, Overview V2, Discover and company functionality are implemented; real-browser visual validation remains pending.
Files changed: landing.py, auth_pages.py, static/premium.css.
Tests: 19 existing landing/auth/security/UI checks and 2 new premium checks passed.
Diff whitespace validation passed.
Commits: pending first premium checkpoint.
Manual browser review: still pending; no new browser dependencies installed.
Known issues: no visual smoke claim; implemented application views still require desktop/tablet/mobile browser validation.
Original landing/auth checkpoint and subsequent workspace implementation are retained. Phase 24P.0 is fully completed with JavaScript runtime verification; browser visual validation remains pending.

## Phase 24S.2B.4 - Completed

Phase 24S.2B.4 is completed. This documentation-only closure changes no other phase status or roadmap item.

HTTP subsystem protection summary:

- SSRF protection validates public destinations, guards DNS resolution and the connected peer, and preserves TLS verification.
- Gzip/deflate decompression is bounded, with wire-size limits on received responses.
- Authentication dispatch quotas bound authentication-related request dispatch.
- Cleanup is finite; `PublicIPError` is classified as permanent rather than retried as a transient failure.

Reported full offline regression:

- `1817 passed`
- `7 skipped`
- `440 subtests passed`
- `FULL_REGRESSION_EXIT=0`

The independent final read-only security audit found zero confirmed remaining P0/P1/P2 findings within the reviewed HTTP subsystem. This is a scoped static-review conclusion, not proof of the absence of vulnerabilities or verification of live DNS, peer, TLS or production behavior. The reported regression and audit were not rerun for this documentation-only closure.

No production deployment was performed as part of this closure. Existing work and all other roadmap statuses are preserved.

PRODUCTION_TOUCHED=False


## Read-only UI audit status and Phase 24P planning baseline

The recently completed read-only UI audit records the following as implemented in the existing application: public landing, authentication pages, premium authenticated SaaS shell, Overview V2, Discover and tender details, company creation/editing/onboarding, existing Saved functionality, and the existing PDF assistant workflow. This is implementation status, not a claim of real-browser visual acceptance. Landing/auth/SaaS shell/Overview V2/Discover/company/PDF desktop, tablet and mobile visual validation remains pending. Existing Saved and PDF behavior must be preserved; no missing service is implied to have been added by this documentation update.

All earlier completed milestones, reported test results and the completed Phase 24S.2B.4 security checkpoint remain intact. Their tests and security audit have not been rerun here. Phase 24P.0 filter ownership is fully completed and runtime-verified as recorded below. 24P.1 is COMPLETED as a static evidence audit below; 24P.2 presentation is implemented with browser acceptance blocked as recorded below; 24P.3-24P.6 remain PLANNED. No dashboard visual acceptance is claimed.

## Phase 24P Premium Analytics Dashboard specification - PLANNED

### Visual and interaction specification

The user APPROVED the rich, sophisticated enterprise procurement analytics command center inspired by their first dark navy dashboard screenshot. The earlier simple visual sketch was REJECTED and is not the implementation target. Adapt the approved visual composition to real supported procurement data; screenshot values are never application data. Build a compact left sidebar with clear active navigation and a topbar containing active organization, company and explicit date/data scope. Use deep navy layered surfaces, indigo/blue/violet accents, refined low-contrast borders that still meet accessibility requirements, restrained elevation, elegant typography and consistent spacing.

The desktop composition uses an elegant asymmetric grid with varied chart sizes and widget treatments: six truthful KPI cards (Discovered, Matched, High Fit, Active Sources, Countries, Closing Soon); a large Tender Activity grouped bar/area chart; multi-ring Company Fit distribution; Global Geography with country names, real counts and horizontal bars; separate industry, category and source breakdowns; a deadline calendar heatmap; Source Health and Data Completeness widgets; and a professional sortable Top Opportunities table. Add compact contextual summaries and actionable business widgets for available opportunities, deadlines and metadata gaps, with supported navigation to existing workflows. Visual richness must come from composition and real data, including polished unavailable states where a requested visualization has no supported input. Rings represent clearly labeled fit bands over one declared population; they must not imply independent additive populations. Geographic bars show an explicit numerator and denominator. Each chart has a textual summary and accessible table/list alternative. No visual reference values become product data.

Desktop uses the compact premium sidebar, organization/company topbar and asymmetric multi-column dashboard grid. Tablet collapses navigation and reduces chart/widget columns. Mobile uses an accessible navigation drawer, stacked KPI/chart/widget layouts and usable date/filter controls without page-level horizontal overflow. Charts adapt label density without hiding the underlying accessible data. Support keyboard-only navigation, visible focus, meaningful accessible names, ordered headings, Escape and focus restoration for drawers/dialogs, keyboard-operable chart filters, non-color-only legends, sufficient contrast, reduced motion and usable touch targets.

### Data truth, scope and preservation contract

- Always distinguish latest successful search / browser-session discovery metrics from persisted history. A last-search count is not lifetime activity; a session timestamp is not a tender publication date. Show the data origin, population, organization/company scope and effective date range near metrics and charts.
- Preliminary company fit is separate from full AI scoring, document completeness and analysis readiness. Matched and High Fit require explicit audited fit eligibility rules and an existing supported threshold; display those rules and unscored/unknown records separately. Do not infer full AI scoring from preview fit.
- Discovered counts unique eligible tenders within the declared population and documented deduplication key. Active Sources means sources with verified successful results in that population, not all configured adapters or global source coverage. Countries counts known country values in that population and identifies unknown values. Closing Soon requires real parseable deadlines and a displayed upcoming window/timezone.
- Audit which persisted records, timestamps, scoring fields, source reports and APIs actually exist before deciding which metrics are available. Never fabricate revenue, savings, growth, alerts, saved tender counts, historical data, source coverage, counts or timelines. Saved counts require a real authorized existing data source; do not derive them from search results.
- Every KPI, chart, percentage, table cell, summary and date must be traceable to real supported application fields or a documented computation over authorized records. Percentages require a visible denominator and unknown/excluded counts; missing denominators are unavailable. Tender values and currencies are shown only when present, without unsupported conversion or combining incompatible currencies. Data Completeness uses audited metadata requirements and explicit present/required counts, independently of company fit and full AI scoring.
- Missing/unavailable data displays an honest unavailable state with a reason, such as "No persisted history available" or "Deadline unavailable". Use zero only for a verified empty population from a successful query. Loading, error, partial, unknown and unavailable must remain distinct. Failed sources are not zero-result sources.
- Date controls must declare the filtered timestamp (for example publication, discovery persistence or deadline), inclusivity, timezone and missing-date handling. Unsupported ranges or series are unavailable; never stretch a last search into historical trends, interpolate missing observations or invent earlier buckets. A company change cannot silently reuse fit results computed for another company.
- Preserve authentication, organization/company boundaries, viewer rights, existing API contracts, abort/epoch stale-request guards, existing Saved, PDF assistant, discovery repeatability and partial/total source failures. Aggregate only data the caller is already authorized to access. Do not mutate seen-state, saves or scoring when viewing analytics.
- Interactive chart filters and drilldowns must open authorized Discover results with supported source/country/industry/category/fit/date predicates and the same declared population. Validate available filter contracts in 24P.1; if Discover cannot reproduce a predicate or historical population, explain the limitation and disable that drilldown rather than imply equivalent results. Keyboard controls and clear/reset actions expose the same behavior as pointer interactions.
- Billing, automatic document acquisition, additional procurement sources and missing backend/product services remain out of scope. No production, network, DNS or secrets work is part of this documentation update.

### Numbered implementation milestones

#### 24P.0 - FULLY COMPLETED - Resolve Discover filter ownership (runtime verified 2026-10-10)

- Goal: remove conflicting ownership of Discover source/currency filters between `premium.js` and `discovery.js`; establish one owner and stable values/options/labels derived from actual fetched data. Static premium catalogs must not imply fetched source coverage or available currencies.
- Changed files: `app/api/static/premium.js`, `app/api/static/discovery.js`, `tests/js/discovery.test.cjs`, `tests/test_premium_ui.py`. Existing stable markup selectors are reused; no markup/API changes.
- Dependencies: current discovery response metadata and workspace/report lifecycle; no new API or service. Inspect both scripts before changing ownership.
- Acceptance criteria: one filter owner; deduplicated deterministic options and readable labels from fetched metadata; existing all-source/all-currency choices preserved; a still-valid selection survives refresh, an invalid selection resets explicitly; missing values are handled honestly; navigation and workspace changes cannot reinsert static options or stale data. Failed/attempted sources remain visible in source health without being represented as fetched results.
- Tests: repeated reports, refresh/navigation, mixed source/currency values, duplicate and missing metadata, empty/partial/total failure, selection retention/reset, company/organization switch and out-of-order responses; existing Discover and premium UI regressions.

Verified implementation results (2026-10-10):

- `discovery.js` exclusively owns source/currency options. Removed premium catalog hydration, navigation timers and DOM observer; premium navigation and Overview behavior remain intact.
- Options come only from fetched item metadata, are deduplicated and sorted by unchanged API values. Known source identifiers have stable readable labels; unknown identifiers and currency codes remain literal. Empty/blank/non-string metadata does not become an option. All fetched sources / All currencies labels remain stable.
- Refresh preserves available selections and explicitly resets unavailable selections to the all choice. Selects are disabled during loading. Workspace identity changes, empty reports, total failures and HTTP/network errors clear obsolete options. Partial source failures remain in source health and do not create filter entries. Existing request serial/abort/context guards remain; the error path also checks workspace identity.
- Runtime: official portable Windows x64 Node.js LTS **v24.21.0**; no global installation, administrator rights, npm install or dependencies. Downloaded only from `https://nodejs.org/dist/` (release index, archive and official `SHASUMS256.txt`). Archive `node-v24.21.0-win-x64.zip` SHA256: `158f7685b44de51f6c0df1d153526cbcd3e1bc739a8dfc607721cef75de9e541`; exact match to official checksum verified before extraction. PowerShell HTTPS and curl Schannel initially failed; Python urllib with normal TLS verification succeeded.
- `node --check` on all **7** `app/api/static/*.js` and **5** `tests/js/*.cjs`: PASS, exit 0. All five JS regressions PASS, exit 0: `company.test.cjs` (generated dashboard HTML), `discovery.test.cjs`, `discovery_full_ai.test.cjs`, `phase24r.test.cjs` (generated dashboard HTML), `shortlist_ui.test.cjs`.
- Strengthened Discover regression loads both actual `discovery.js` and `premium.js`, dispatches hash/workspace events with multiple listeners, and verifies combined source/currency predicates, deterministic/deduplicated options, literal unknown/prototype-name/padded identifiers, absent/blank/non-string metadata, selection retention/reset, loading disable/re-enable, organization/company/epoch changes, out-of-order success and stale network rejection, partial/empty/total failure, HTTP 403/409/500 and 401 login redirect. Existing Saved/PDF rendering, viewer guards and navigation/failure regressions also pass.
- Focused Python: `pytest.main(['-p','no:cacheprovider','--basetemp',<new dedicated directory>,'-q','-rs', ...])` for `test_premium_ui.py`, `test_currency_ui_contract.py`, `test_saas_core.py`, `test_saved_ui_contract.py`, `test_discovery_full_ai_contract.py`, `test_web_auth.py`: **28 passed**, no skips/deselections/errors, exit 0. The previously excluded `test_company_profile_ui_preserves_constraints` passed. Final rerun adding `test_phase24r_ui_audit.py`: **42 passed**, exit 0; one existing Starlette deprecation warning and one pytest assertion-rewrite warning caused by importing dashboard HTML before pytest initialization.
- Runtime/temp environment workaround: this shell's child Python did not retain the prepended PATH, so portable Node was added to `os.environ['PATH']` inside the Python test launcher. TEMP/TMP and pytest `--basetemp` pointed to newly created, separate `.phase24p0-tests-*` directories. Existing project temp directories and inaccessible system pytest temp were not touched.
- Broader relevant offline regression (33 files): **282 passed, 1 skipped, 390 subtests passed**, one existing Starlette deprecation warning, exit 0. Selected files: `test_premium_ui`, `test_currency_ui_contract`, `test_saas_core`, `test_saved_ui_contract`, `test_discovery_full_ai_contract`, `test_web_auth`, `test_phase24r_ui_audit`, `test_responsive_ui`, `test_organization_api`, `test_organization_companies`, `test_organization_data`, `test_organization_workflows`, `test_organization_pdf_rag`, `test_discovery_history_api_behavior`, `test_discovery_history_api_contract`, `test_discovery_history_repository`, `test_discovery_preview_scoring`, `test_shortlist_api_behavior`, `test_shortlist_api_contract`, `test_shortlist_integration`, `test_shortlist_repository`, `test_session_access`, `test_auth_api`, `test_company_profile_pdf`, `test_company_profile_pdf_ui`, `test_pdf`, `test_rag`, `test_rag_ingestion`, `test_currency_normalization`, `test_source_health_api_behavior`, `test_source_health_api_contract`, `test_source_health_ui_contract`, `test_search_history_ui_contract` (all under `tests/`, `.py`). Covers tenant/company isolation, membership revocation, viewer restrictions, cross-origin/authentication checks, discovery repeatability, Saved persistence and PDF/RAG behavior using offline fixtures. Skip: Windows symlink privilege unavailable in `test_rag_ingestion.py:236`.
- Initial broad offline guard incorrectly blocked Windows asyncio's internal loopback socketpair: **92 failed, 182 passed, 1 skipped, 8 errors**, exit 1. A focused diagnostic reproduced the guard exception at `socket.socketpair()`. Corrected only the test launcher to allow numeric loopback while blocking external sockets and DNS; the identical 33-file selection then passed as above. No application defect required another implementation change. Temporary incomplete DOM stubs while adding the two-script JS test were corrected and the final five JS regressions and 42 Python checks rerun successfully.
- All changed source/test/documentation diffs inspected; `git diff --check`: PASS. No remaining 24P.0 blocker. Real-browser visual/mobile validation and the entire unrelated full suite were not run; no visual, live procurement, live Saved/PDF or production readiness claim is made.
- Portable runtime and newly created test artifacts retained under ignored `.cache/phase24p0-local/` for local testing only. No API/security/backend/Saved/PDF implementation changes, other-phase implementation, global installations, external data requests, secrets access, production changes, migrations, commit, push or deployment. The approved Premium Analytics Dashboard specification and milestones 24P.1-24P.6 are preserved.

#### 24P.1 - COMPLETED - Audit real analytics data and tenant scoping

- Goal: inventory existing persisted history versus latest-session discovery, APIs, timestamps, identifiers, preliminary fit/full AI scores, source status and role/tenant boundaries. Produce a supported-metric mapping before implementation, covering all six KPIs, Tender Activity, Company Fit, Global Geography, industry/category/source breakdowns, deadline calendar, Source Health, Data Completeness, Top Opportunities columns, contextual summaries and Discover drilldown predicates.
- Affected files (read-only audit targets; any future edits limited to evidenced needs): `app/api/organization_workflow_routes.py`, `app/api/organization_data_routes.py`, `app/api/scoring_run_routes.py`, `app/organizations/models.py`, `app/organizations/repository.py`, `app/database/repository.py`, `app/scoring/models.py`, `app/api/static/shell.js`, `app/api/static/discovery.js`, `app/api/static/history.js`, `app/api/static/saved.js`; mapping recorded in `PHASE24_PROGRESS.md`.
- Dependencies: 24P.0; existing API/model contracts and authorized organization/company context.
- Acceptance criteria: each proposed metric maps to actual fields, API, persistence/session lifetime, timestamp semantics, deduplication, company applicability and permissions; unsupported metrics explicitly unavailable. Record exact available tender metadata, completeness requirements, fit thresholds/bands, chart denominators and supported Discover filter/navigation contracts, including whether a drilldown can reproduce the aggregate population. Audit determines whether company-scoped history/fit and historical source reports exist rather than assuming them.
- Tests: existing discovery history API/repository, organization data/workflow and scoring contract tests; targeted read-only fixtures for no history, missing dates, unauthorized/cross-tenant access and company-specific score eligibility. Record gaps without inventing services.

### 24P.1 evidence and metric decision matrix (2026-10-10)

Audit completed as a documentation-only source/contract review. Completion means every requested metric has an evidenced supported computation or an explicit unavailable decision; it does not mean every requested widget has supported inputs or has been implemented. No new service, runtime acceptance, production data inspection or visual acceptance is claimed. The interrupted audit's known findings were checked against local source; missing evidence was inspected in bounded excerpts. No network, secrets, broad test suite, application mutation, commit or deployment was used.

#### Evidence register and populations

References below are repository paths and line anchors at this audit checkpoint.

- **D: current discovery report** ? `app/api/organization_workflow_routes.py:1316-1505`, `app/api/schemas.py:104-198`, `app/monitoring/service.py:347-380`. `POST /api/v1/organizations/{organization_id}/discover/tenders` resolves the caller's active shared company, fetches configured sources with company monitoring keywords and configured per-source/feed limits, then applies `prefilter_notice`. These are returned company-prefiltered opportunities, not all notices in the procurement market. The browser holds `items`/`report` in `discovery.js:322`; refresh/new search clears them, organization/company/epoch changes abort and reset them (`:323-327,682-685`). No response timestamp exists. `premium.js:10` records local receipt time, not publication or database creation. Explicit `snapshots` mode uses the existing connector store (`organization_workflow_routes.py:1358-1366`); normal UI POST does not request it. Merely opening analytics must not issue this POST or mutate seen-state.
- **H: persisted search events and snapshots** ? workflow routes `:61-79,266-340,1029-1167,1421-1505`; `app/database/repository.py:750-1025`. `GET .../discovery/history?limit=N` returns summaries for the active company; default 50, repository clamps to 1..100, ordered `created_at DESC,id DESC` (`repository.py:909-954`). There is no offset/cursor, total-count or date-range API. `GET .../discovery/history/{id}` returns the stored `snapshot_json` as `discovery`; organization and active-company checks prevent loading another company's ID. Fields: `id`, `organization_id`, `company_id`, `created_by_account_id`, `result_count`, `scored_count`, attempted/successful/failed source lists, partial/total failure flags, `created_at`. Event time is server UTC ISO timestamp at persistence (`repository.py:798-802`), not publication or first discovery of a unique tender. Repeated searches are separate events. A successful response can have `history_id=null` when storage is missing/fails; absence of history therefore does not prove no searches occurred. Snapshot decode failure is 503, not empty data. History UI fetches 50 (`history.js:180`) and renders its own snapshot; it does not hydrate Discover.
- **O: shared public opportunity cache** ? `app/sources/opportunities.py:1,14-59,69-105`. `source_opportunities` stores `(source_id,external_id)` identity, `notice_json`, `connector_version`, `first_seen`, `last_seen`; UTC first/last synchronization times. Upsert overwrites the current notice and `last_seen`, retaining `first_seen`; this is not a revision timeline or tenant discovery history. Read scans at most the latest 1000 records per source and returns a capped 1..100 selection. No authorized dashboard listing/date aggregation API for this store was found in the inspected existing contracts. Public-cache counts cannot substitute for company discovery counts, source reachability or global coverage.
- **R: durable metadata scoring** ? `app/api/scoring_run_routes.py:28-77`, `app/scoring/runs.py:24-29,76-177,201-229`, `app/database/schema/scoring.sql`. POST/GET `/api/v1/organizations/{organization_id}/companies/{company_id}/scoring/runs[/{job_id}]` uses account + organization + company `JobScope`. Snapshots carry profile digest, engine version, configuration, source counts, candidate count and immutable selected revisions; results carry source/external identity, ordinal, score, completeness, scoring JSON and `calculated_at`. GET requires a known job ID, current membership/company and unchanged profile digest; changed profile yields 409. GET is paged (limit 1..100, offset 0..500, at most 500 candidates); complete is true only for succeeded/materialized results. Returned items have identifiers and sanitized scoring, not tender bodies or calculation timestamps. No run-list API or historical trend API here. Handler uses `score_metadata_preview`, not document AI. `source_state=empty_or_not_synchronized` cannot distinguish healthy-empty from unsynchronized. Never merge R with D/H scores by identifier alone or call R full AI.
- **S: Saved** ? workflow routes `:51-58,821-1025`; repository shortlist methods `:490-748`; `saved.js:1,16-20,57-58`. `GET .../shortlist` is active-company scoped; records have ID, organization/company, opportunity snapshot and created/updated timestamps. Save/remove are real mutations for owner/admin/member, not viewer. Saved totals require an authorized shortlist response and its actual limit, not counts inferred from D/H; snapshots may be older than current discovery. Saved and PDF are separate populations.
- **P: PDF analyses** ? `app/api/organization_data_routes.py:326-354,373-479`, `repository.py:198-403`. `/tenders` (default 10, maximum 20) and `/tenders/{id}` read organization-owned analysis records. PDF storage identity uses organization owner + PDF SHA256, not company ID; `/analysis/pdf` needs owner/admin/member and an active company for scoring. Stored analysis/scoring is not proof of current-company applicability: `profile_name/profile_version` are not a company foreign key or immutable digest. Do not count these organization-wide records as company discoveries, saves or current fit. Full-analysis fields in D (`full_ai_analyzed`, `full_analysis`, `full_scoring`, record/hash/filename/truncation/warnings) are optional explicit uploaded-document results; fresh discovery sets full_ai_analyzed=false. History persists the original report, not subsequent in-browser PDF enrichment.

For the matrix, **U** means distinct valid `(source,external_id)` identities in one declared successful D report or one explicitly selected H snapshot. The normalized model explicitly defines this identity (`app/sources/models.py:22-24`). Exclude missing identities with a separate count; never deduplicate by title, URL, tender number or buyer. For multiple selected H events, choose the newest event per identity (`created_at`, then event ID; deterministic first occurrence within an event), disclose event count and duplicate count, and label this a union of retrieved snapshots. It is not lifetime discovery. Existing `result_count` and browser item count count rows, not a guaranteed unique population; deduplication is a future analytics computation, not an audited existing counter. Conflicting duplicate payloads must be disclosed. All percentages below use the post-filter U and state numerator, denominator, unknown and excluded counts. A successful empty population may yield count 0; a zero denominator yields unavailable percentage. Total source failure, unauthorized/error response, corrupt snapshot or unloaded population yields unavailable, never 0. Partial results remain labeled incomplete.

#### Metric matrix

| Metric/widget | Exact input, computation and provenance | Persistence, scope/time and limitations |
| --- | --- | --- |
| Discovered KPI | `count(U)` from D.items or H.discovery.items; H.result_count is only an event row-count cross-check. | D is session/latest search; H is selected persisted company search(s). Retrieval is capped; no lifetime/all-market/newly-seen claim. Partial searches count returned opportunities only. |
| Matched KPI | Returned D records already passed company prefilter (`monitoring/service.py:372-378`); label `Company-prefiltered opportunities` if using count(U). `scored_count` / non-null `preliminary_scoring.fit_score` means scored, not matched. | No audited overall matched cutoff exists. A KPI meaning `fit above matched threshold` is unavailable pending an explicit product threshold; neither score >0 nor category criterion matched can silently become overall eligibility. Stop factors are separate, not automatic dashboard disqualification. |
| High Fit KPI | `preliminary_scoring.fit_score` is available; count with a declared future threshold would be computable. | No existing overall High Fit threshold/bands in Discover (numeric minimum input only). High Fit is currently unavailable, not a hardcoded 70/80 count. Category criterion threshold 65 is not overall High Fit. Historical fit is profile-at-search, not a current-profile recomputation. |
| Active Sources KPI | Distinct `successful_sources` in the declared D/H event(s); show `Successfully reached sources`. If meaning sources yielding eligible results, use distinct U.source intersect successful_sources and label that narrower numerator. | Successful empty source is reached; configured/enabled/attempted is not successful. Date-filtering tender rows must not relabel search-level health as measured in that publication range. Union across H means succeeded at least once in retrieved events, not currently healthy. |
| Countries KPI | No `country` field in TenderDiscoveryItem/TenderNotice; `region` is free-text geography, source catalog `jurisdictions` describes adapter coverage. | Unavailable. Do not infer tender country from source label, buyer, currency or coverage (TED spans jurisdictions). Unknown tender-country count is count(U), not zero countries. |
| Closing Soon KPI | Count unique U with unambiguous parseable deadline in a displayed future window. Recommended future contract: UTC instants `[as_of,as_of + W days)` with explicit W and as_of; date-only values use separately labeled calendar-day window. | `deadline` is optional source string; no existing Closing Soon window or common date normalizer. W and timezone are decisions for implementation, not existing thresholds. Unknown/invalid/ambiguous source-local dates separate; expired records excluded. Never count all deadlines before upper bound, including past dates, as closing soon. |
| Tender Activity | H event series can bucket `created_at`: search count and sum(result_count/scored_count), clearly labeled returned/scored row occurrences. A unique-tender bucket can instead compute per-bucket distinct identities from loaded snapshot details. D publication distribution uses valid `published_at`. | H is UTC persistence activity, not procurement publication/market growth. Repeated tender occurrences across buckets are not globally additive unique counts. Max 100 events and no range/total pagination: disclose retrieved interval/truncation possibility; missing event buckets are unobserved, not verified zeros. Publication distribution of one sample is not acquisition activity. Area/trend interpolation and lifetime growth unavailable. |
| Company Fit distribution | Finite `preliminary_scoring.fit_score` values; denominator scored U, also show unscored/count(U). Exact-score histogram or explicit numeric ranges can be computed. Multi-ring shares must be disjoint bands with one denominator. | Semantic Low/Medium/High bands have no existing contract: unavailable until declared. Separate preview from full_scoring and R; never mix stages/profile identities. H provides historical profile_name/version but not digest or a current-company-score guarantee after edits. |
| Global Geography | No supported tender-country classification. Region text may be listed verbatim as `Reported region` with known/missing counts. | Country names/bars/map/country drilldown unavailable; no geocoding or source-to-country substitution. Region share = records with exact region / count(U), with missing separate; it is not country share. |
| Industry/category/source | Source: exact U.source counts, share count(source)/count(U), missing separate. | Industry/category classification fields absent. `procurement_object` and scoring criterion `category` represent text/relevance, not an industry taxonomy. Industry/category charts and filters unavailable. Source breakdown is returned opportunities, not raw fetched `notice_count` or all configured adapters. |
| Deadline calendar and upcoming list | Bucket U.deadline by declared local calendar date only after unambiguous parsing; daily distinct counts, sorted upcoming records; show unknown/expired counts. | Preserve source strings alongside normalized presentation. ISO aware dates can be converted; naive/source-local and `dd.mm.yyyy` strings supported in O validation are not guaranteed JS Date.parse-compatible. No universal timezone mapping exists. Date-only values do not assert a closing instant. Unsupported parses remain unavailable, not auto-converted. |
| Source Health | D/H `source_statuses`: source/display_name/transport/jurisdictions/languages/homepage_url/official/enabled/authentication_required/state/notice_count/duration_ms/error_type/message, plus attempted/successful/failed and partial/total flags. GET `.../discovery/source-health` returns organization/company/name, history_id,last_checked,sources without probing (`workflow:1172-1309`). | Latest persisted company search, not necessarily browser's newest successful report. last_checked=H.created_at. States healthy/failed/disabled/not_checked distinct; source notice_count is before company-prefilter, not U count. No history means unchecked/disabled catalog state and null time. Older snapshots may lack detailed timings/statuses; fallback from persisted success/failure lists cannot invent duration/counts. Historical events support observed status lists, not uptime/SLA, latency percentile or continuous monitoring. |
| Data Completeness | `preliminary_scoring.completeness_percent`, recomputable as `round(100 * present_groups / 10)` using `metadata_analysis` and `engine.py:465-481`. Aggregate present groups / `(10 * count(U))`; show records with available analysis and exclusions. | Ten groups listed below. This is analysis-field coverage, not required-document readiness, document acquisition or fit. Fresh metadata-only mapping populates at most five groups; 100% is not expected. Individual percentage rounding follows Python round. Missing analysis means unknown, not 0/10. Full document completeness must be a separate labeled stage. |
| Top Opportunities | Identity/title/source/url/tender_number/customer/region/published_at/deadline/initial_price/currency/summary/reasons, metadata_analysis, preliminary_scoring.fit_score/completeness_percent/criteria/stop_factors/missing_information; optional full-document provenance only when actually present. | Country/industry/category cells unavailable. Current ranking (`discovery.js:285-297`): preliminary fit descending, completeness descending, stable input ties. Future analytics should explicitly put null/nonfinite last and tie-break by identity (current Number(null) coercion must not become eligibility). Show finite zero score/value honestly. Monetary totals only within one known currency; no FX or cross-currency sum. Publication recency only valid published_at; H.created_at is search recency, S timestamps save recency, P timestamps analysis recency. No invented AI ranking, win chance or current tender lifecycle status. |
| Contextual summaries/actions | Derive returned/unique/scored/unknown/source-failure/deadline/coverage counts from same population and formulas; show exact scope. Existing detail, official safe HTTP(S) link, Saved and PDF navigation/actions may be reused. | No fabricated alert inbox, growth, savings, revenue, predicted wins or auto-acquired documents. Do not imply a historical row is loaded in current Discover. Saved badge/count requires S; PDF action requires explicit uploaded document and write role. |

**Scoring formula and completeness evidence.** `preview.py:25-173,184-230` uses profile product keyword matches in title/procurement_object/technical text: no match=0; title match=70; primary-object (first 350 chars) match=60; contextual match=35; supply-intent with match adds 10; service-only without supply/title match caps at 20; clamp 0..90, round to one decimal. Category criterion is matched at >=65, partial at >0, otherwise failed; fit_score is overwritten by metadata relevance. This is deterministic preliminary product relevance, explicitly never win probability (`models.py:118-130`, `engine.py:485`). Other criteria/stop factors and scorable_weight remain separate. Full rule scoring instead computes `round(100 * earned_points / scorable_weight,1)` over criteria whose status is not not_scored; zero weight gives null (`engine.py:516-530`). Neither formula supplies a High Fit product threshold.

Completeness groups: (1) any title/tender_number/customer; (2) initial_price is not None (zero counts); (3) submission_deadline; (4) contract_term; (5) delivery_region or delivery_address; (6) any bid/contract security amount/percent is not None; (7) procurement_object or quantity; (8) participant_requirements; (9) required_documents; (10) technical_requirements. Currency, publication, URL and summary alone are not additional groups. `services/tender_analysis.py:54-100` maps notice title/number/customer/price/currency/deadline/region/summary to analysis fields (summary -> procurement_object), with trimming; contract/security/requirements/documents/technical remain unknown. Show these gaps without inventing required tender documents.

#### Discover drilldown contract

`discovery.js:7-17,322-327,687-688` owns local predicates over its current fetched items; the API receives no dashboard predicates. `#discover` is navigation only, not an encoded filter/population URL or history replay interface. No public setter for report/items/filter state exists (`publicApi:310-318`). Thus predicate computation is supported locally, but automatic dashboard handoff still requires future UI integration and the same report identity. Disable any drilldown that cannot preserve the aggregate population rather than rerun discovery and imply equivalence.

| Predicate | Existing exact behavior and limit |
| --- | --- |
| Keyword | Case-insensitive substring over title + summary + metadata_analysis.procurement_object; not semantic/global search. |
| Source | Exact API source equality; options from fetched metadata only. Source breakdown on same D can be reproduced after explicit filter handoff integration. |
| Buyer | Case-insensitive substring in customer; no buyer ID grouping/equality contract. |
| Currency/value | Exact currency equality; minimum initial_price inclusive only when currency selected and non-null. No conversion. |
| Fit | Minimum preliminary fit inclusive; null excluded. No maximum, semantic band, full-score or stop-factor filter. High band could use minimum only after threshold exists; middle/low exclusive ranges cannot be reproduced. |
| Deadline | Parseable deadline <= selected date + `T23:59:59Z`; missing/unparseable excluded. No lower bound. Cannot reproduce upcoming window or precise calendar-day cell; fractional seconds after 23:59:59 also exceed current end boundary. |
| Publication | Parseable published_at >= Date.parse(selected date), inclusive; no upper bound. Cannot reproduce arbitrary bounded range or a day bucket. |
| Country/region/industry/category | No local controls/predicates. Disabled/unavailable. |
| History/search-time/durable-run population | No Discover replay/search-time filters or R hydration. History has separate read-only snapshot detail; navigate there for H, not to a newly fetched Discover report. |

Future bounded timestamp filtering should declare `[start,end)` and timezone, convert only known instants, preserve unknown counts, and never claim the current one-sided Discover controls implement that contract. Date-only strings and source-local naive times require an explicit policy before inclusion. No default deadline window, universal country mapping or semantic fit bands were added by this audit.

#### Authorization, eligibility and verification limits

- All aggregates must resolve authenticated current membership and authorized company before reads; do not trust browser company labels or caller-supplied scope. D/H/S use active company, H/S repository rechecks organization + company, P reads organization-owned records, R uses account + organization + explicit company and current digest. Unauthorized reads are errors, not empty populations. D/H 409 means no active company; invalid/cross-company history ID is 404; storage failures are unavailable. Never reuse fit/cache after workspace/epoch changes.
- **Viewer clarification:** viewer is read-only for business mutations (company editing, save/remove, PDF analysis); reads of existing H/S/P/source health are allowed with membership. However `discover/tenders` permits any authorized active-company member, and history recording calls `_require_org_role` without a write-role set (`repository.py:813-817`). A viewer-triggered search can therefore persist a history event. R enqueue also checks membership/profile without an explicit write-role gate in inspected routes/service. The blanket claim that viewer cannot cause any persisted work is unsupported. Do not change these existing contracts in this audit; dashboard read/render must not invoke discovery, R enqueue, save or PDF analysis. UI viewer mutation guards are not a substitute for backend checks.
- H historical fit belongs to recorded company/profile at search, with profile_name/version but no immutable digest; edits invalidate a claim of current fit unless explicitly labeled historical. R validates digest and engine; P stored scoring lacks company binding. Matching by company name alone is unsafe. PDF hash/record ID proves document provenance, not a current-company scoring relationship or current version of procurement documents.
- Targeted existing fixture evidence inspected (not rerun): `tests/test_discovery_history_api_behavior.py:64-223` covers stored snapshot, company switch yielding empty list/404 and outsider 403; `test_discovery_history_repository.py:92-209` covers repeat events, ordering, company isolation and membership; `test_discovery_full_ai_contract.py:56-73` distinguishes metadata-only default and full-document snapshot fields; `test_discovery_preview_scoring.py` includes high product relevance, incidental service cap, no 100% preview and no duplicate-keyword inflation. Earlier 24P.0 test results remain historical evidence only. Static branches establish missing dates/nulls, empty vs failed states, caps and scoring eligibility; no new runtime/test pass is claimed for 24P.1.
- Audit gaps are explicitly resolved as unavailable/conditional above: country/industry/category fields; overall Matched/High Fit thresholds and bands; complete lifetime/date-range history; Discover history/range drilldowns; universal deadline timezone normalization; source uptime; current-company binding of organization PDF scores; run listing and tender bodies in R. These are implementation constraints, not evidence that new services were built. 24P.2-24P.6 remain PLANNED.

#### 24P.2 - IMPLEMENTED, acceptance BLOCKED - Responsive premium shell and six KPI cards

- Goal: implement the approved rich navy command-center shell, asymmetric widget grid and the Discovered/Matched/High Fit/Active Sources/Countries/Closing Soon cards with truthful scope/origin labels and all loading/error/unavailable states.
- Affected files (future implementation): `app/api/saas_shell.py`, `app/api/static/premium.css`, `app/api/static/premium.js`, `app/api/static/shell.js` only where context integration requires it; `tests/test_premium_ui.py`, `tests/test_saas_core.py`.
- Dependencies: 24P.1 supported-metric mapping; existing auth/navigation/context; 24P.3 is required before cards can claim live aggregate results. This milestone may build unavailable-state presentation first.
- Acceptance criteria: compact premium sidebar, organization/company/date topbar, layered deep navy surfaces, indigo/blue/violet accents, elegant typography, varied widget sizes and six responsive cards match the approved first-screenshot direction; the rejected simple sketch is not an acceptance baseline; no fabricated sample figures in the authenticated product; desktop/tablet/mobile reflow, meaningful labels, visible focus and accessible navigation; existing routes, onboarding and controls work.
- Tests: shell/markup regressions, keyboard and focus checks, loading/no-company/unavailable/error cases; real-browser layout checks at representative desktop/tablet/mobile widths remain required, with results recorded only when actually run.

#### 24P.3 - PLANNED - Secure true-data aggregation engine

- Goal: implement every missing premium analytics data capability identified by 24P.1 through the ordered checkpoints below, then aggregate verified data using declared populations and consistent filters. Reuse existing contracts where sufficient; extend models/APIs only for evidenced gaps. Audit-time unavailable decisions describe the current implementation, not permanent exclusions from Phase 24P.
- Affected files (future implementation, conditional on audit): `app/api/organization_data_routes.py`, `app/api/organization_workflow_routes.py`, `app/api/schemas.py`, `app/organizations/repository.py`, `app/database/repository.py`, `app/api/static/premium.js`; `tests/test_organization_data.py`, `tests/test_organization_workflows.py`, discovery history API/repository tests.
- Dependencies: 24P.1 evidence/authorization contract and 24P.2 display contract. Missing capabilities must be implemented through 24P.3.1-24P.3.9; no synthetic observations or retroactively invented history.
- Acceptance criteria: authorized tenant/company scoping enforced before aggregation; viewer read access follows existing rights; deterministic deduplication and explicit null/unknown treatment; preliminary fit never substituted for full AI scoring; supported empty queries may return zero, unavailable inputs cannot. No invented counts/timelines, cross-tenant cache leakage or analytics read mutations; workspace/request epoch invalidates stale responses.
- Tests: known-fixture aggregate correctness, duplicates/nulls/date boundaries/timezones, partial data, empty versus unavailable, cross-tenant and company isolation, viewer rights, unauthorized requests and stale-context races; regression of existing API responses and discovery repeatability.


##### Ordered engineering checkpoints (all PLANNED)

Owner-required completion contract: every gap in the 24P.1 matrix has an implementation checkpoint and a verification gate below. Work proceeds in this order; downstream work may render rollout states while dependencies are pending, but cannot be accepted as complete merely because a widget says unavailable. Verified supported source data must produce working countries, classifications, fit bands, history, dates, aggregates and drilldowns. Preserve original values and provenance; never infer tender country from currency, source, source jurisdictions, buyer name or adapter coverage. Never fabricate categories, timestamps, scores, historic events or source observations.

- **24P.3.1 - PLANNED - Authenticated enrichment and versioned contracts.** Depends on 24P.1. Deliver an adapter-by-adapter field-support register and additive normalized notice/discovery/snapshot contracts for verified country, original classification codes, dates and scoring provenance. Reuse the existing authenticated discovery/ingestion path: enrichment must respect membership/company checks and configured connector authentication, with no browser credentials and no connector fetch on dashboard GET/render. Record source/external identity, original field path/value, connector/normalizer version and actual observation time; distinguish source publication/deadline from ingestion and search times. Carry optional enrichment through D, newly written H and O without rewriting old snapshot evidence. Targets: `app/sources/models.py`, supported adapters in `app/sources/`, `app/sources/ingestion.py`, `app/sources/opportunities.py`, `app/api/schemas.py`, `app/api/organization_workflow_routes.py`. Regression: source fixtures, discovery/full-AI contracts and old snapshot decode. Acceptance: each supported adapter fixture retains raw values and provenance end to end; missing/conflicting/unsupported fields remain null with reason; existing response fields and identity semantics remain unchanged. No invented country coverage guarantee for adapters without verified fields.

- **24P.3.2 - PLANNED - Tender-country normalization.** Depends on 24P.3.1. Deliver a versioned explicit-country-code/name normalization table, country semantics (procurement/delivery location, distinct from buyer location), and multi-country/unknown/conflicting handling. Accept only documented source tender-location fields or verified explicit country text with an unambiguous mapping; retain reported region verbatim. Return canonical country codes, original values, evidence and status; geographic unique-tender counts must disclose multi-country membership and need not sum to U. Targets: new `app/analytics/normalization.py`, source models/adapters and schemas. Regression: ISO codes/names/aliases, multi-country, ambiguous region, missing fields, and currency/source-only fixtures. Acceptance: all supported country fixtures map exactly; currency/source-only fixtures stay unknown; country KPI, distribution and equality filters agree on the same U and country policy.

- **24P.3.3 - PLANNED - Supported industry/category taxonomies.** Depends on 24P.3.1-2. Deliver a versioned registry of taxonomy IDs, valid codes, labels, hierarchy and supported mappings for classifications actually supplied by adapters (for example CPV only where verified); preserve raw codes/labels and primary/secondary roles. Industry mapping requires an explicit documented code crosswalk with provenance; unsupported code systems and unmapped industry remain unknown. Never treat procurement text, source identity or scoring criterion `category` as classification. Targets: new `app/analytics/taxonomies.py`, source adapters/models and schemas. Regression: valid/invalid/obsolete/unmapped codes, multiple codes and hierarchy filters. Acceptance: verified category and industry fixtures drive real charts/filters; no free-text guessing; unique-tender membership prevents duplicate inflation and multi-label denominators are disclosed.

- **24P.3.4 - PLANNED - Preliminary fit eligibility and score bands.** Depends on 24P.3.1. Deliver a documented, versioned product policy: eligible = finite metadata-preview score in the engine's documented range, known scoring stage/engine and company/profile provenance; missing/nonfinite/out-of-range or unbound scores are unknown, not zero. Proposed policy to implement and lock in fixtures: Low `[0,35)`, Medium `[35,65)`, High `[65,90]`; Matched = eligible score >=35, High Fit = eligible score >=65. These are new preliminary relevance policy decisions, not audited existing overall thresholds, full AI or win probability. Display stop factors independently; do not silently alter eligibility. New search snapshots capture immutable profile digest, engine/policy version and actual scoring time when known. Old snapshots without digest may show explicitly historical score-at-search bands, never current-profile eligibility; current claims require verified digest or an explicit authorized recomputation, never an analytics GET mutation. Targets: new `app/analytics/fit.py`, `app/scoring/preview.py`/models only for provenance needs, workflow/schemas and snapshot writer. Regression: exact 0/35/65/90 boundaries, null/nonfinite, stale profiles, stop factors and full-document separation. Acceptance: KPIs/rings/table/filter share identical policy; no scoring algorithm change solely to raise dashboard counts.

- **24P.3.5 - PLANNED - Complete paginated company history and scoring retrieval.** Depends on 24P.3.1/4. Deliver additive authenticated history paging with bounded page size, stable `(created_at,id)` cursor, `[start,end)` search-time filters, an as-of watermark, has-more/next-cursor and explicit completeness/storage-error metadata. Bind cursors to authorized organization/company/query; preserve legacy `limit` response behavior via a versioned/additive route. Retrieve snapshot details without silently stopping at 50/100 events; bounded batch reads must retain scoped ID checks. Add authorized R run-list paging and immutable revision-backed tender bodies/calculation provenance where needed for durable-run analytics; maintain account/company/digest restrictions and the existing 500-candidate run cap disclosure. No joining R to D/H by identity alone. Targets: `app/database/repository.py`, `app/organizations/repository.py` where scope resolution requires it, workflow routes, `app/api/scoring_run_routes.py`, `app/scoring/runs.py`, schemas, `app/api/static/history.js`. Regression: >100 history events, equal timestamps, concurrent inserts, cursor tampering, deleted/corrupt snapshots and cross-company/run access. Acceptance: all events inside a fixed authorized watermark are retrieved once with no gaps/duplicates; truncated/incomplete results never claim lifetime totals. Missing storage returns unavailable, not empty history.

- **24P.3.6 - PLANNED - Date normalization and deadline windows.** Depends on 24P.3.1/5. Deliver server-defined normalized dates retaining raw string, parsed instant or calendar date, precision, known timezone/offset, parser version and valid/missing/invalid/ambiguous status. Parse documented source formats; source-local naive values require documented timezone evidence, never machine-local guesses. Define publication, search, scoring and synchronization date fields separately. Closing Soon defaults to a visible configurable W=7-day instant window `[as_of,as_of+W days)` in UTC; date-only deadlines use a separately labeled W-calendar-day window in the displayed IANA timezone, without assigning a fictional closing instant. Return as_of once per population and use the same contract for charts, calendar, filters and table. Targets: analytics normalization, schemas, workflow enrichment and new analytics service. Regression: ISO offsets, verified `dd.mm.yyyy`, invalid dates, leap days, DST, fractional seconds, midnight, expired and exact end boundaries. Acceptance: unknown/ambiguous dates remain separately counted; expired instants are excluded; a deadline heatmap cell and Discover predicate return identical identities.

- **24P.3.7 - PLANNED - Historical aggregates, completeness and observed source health.** Depends on 24P.3.2-6. Deliver deterministic U construction across complete selected H snapshots (newest event then ID, first occurrence), excluded-identity/duplicate/conflict counts, and distinct publication/search/deadline series with explicit bucket/timezone/coverage semantics. Separate search occurrence totals from per-bucket unique tenders and global union totals; never claim all-market or first-discovered history from these samples. Compute six KPIs, country/taxonomy/source distributions, disjoint fit shares, deadline buckets and table totals from shared predicates. Return ten-group metadata completeness with known-analysis denominator, all-U coverage, unknown exclusions and per-group gaps; distinguish enriched country/classification/date coverage and full-document completeness. Preserve the matrix's all-U completeness definition, but mark it partial/unknown when analysis is absent rather than assigning absent analyses zero coverage. Historical source panel aggregates actual attempted/success/failed observations and recorded durations with sample count/interval; uptime/SLA and continuous-monitoring claims remain unsupported without genuine monitoring evidence. Targets: new `app/analytics/service.py`, repository bounded snapshot reads, schemas. Regression: repeated events, conflicting revisions, partial/total failure, missing analysis, zero price, successful empty sources and observed gaps. Acceptance: every fixture numerator/denominator/exclusion reconciles exactly; verified empty covered buckets can be zero, unobserved/error buckets cannot; no cross-currency totals.

- **24P.3.8 - PARTIAL - Secure analytics API and provenance boundaries.** Depends on 24P.3.1-7. Deliver authenticated company-scoped read-only population/aggregate/row contracts (new `app/api/analytics_routes.py` only because current D/H routes lack bounded aggregate/replay queries), with population ID, D/H/R origin, selected event/run IDs, watermark, profile/policy/parser/taxonomy versions, time field/range/timezone, normalized predicates, pagination/completeness, totals/unknowns and capability reasons. Provide replay rows from the same authorized population, never a fresh discovery POST. Validate membership/company before repository/cache access and again on population-token use; bound queries and pages. Cache keys include scope/profile/query/version; epoch changes clear UI state and abort stale requests. Do not serialize credentials, connector errors with sensitive payloads or unauthorized tender bodies. Keep P organization-wide scores separate; where a company-scoped full-analysis feature is exposed, new results require explicit company + immutable profile + document hash/record + engine provenance, while old unbound P results stay organization history. Targets: routes/schemas, repository scope checks, API router registration where required, scoring/PDF persistence only for evidenced provenance gap, `premium.js`/`shell.js`. Regression: auth/role matrix, forged IDs/cursors/population tokens, revoked membership, stale context/profile and read-no-mutation checks. Acceptance: authorized viewers can read; forbidden access is an error, never an empty aggregate; dashboard reads enqueue no jobs, fetch no sources and change no Saved/PDF/history state.

- **24P.3.9 - PARTIAL - Compatibility, justified migrations and rollout gate.** Depends on 24P.3.1-8. Deliver a migration decision record before schema edits: optional normalized fields/provenance inside existing notice/snapshot JSON and derived calculations need no relational migration. Add only evidenced scoped history indexes if query-plan evidence requires them; add nullable company/profile/document bindings for newly persisted full analyses or immutable enrichment storage only if existing JSON/revision storage cannot safely represent the contract. Targets if genuinely required: existing schema files under `app/database/schema/`, actual repository migration/bootstrap path and focused migration tests; do not create a speculative analytics warehouse. Preserve all old raw snapshots and source values; no inferred backfill or destructive rewrite. Additive defaults make old records readable and explicitly unbound/unknown. Acceptance: upgrade an old fixture DB, reread old D/H/S/P/R contracts unchanged, and verify new fields on new records; capability flags document pending/unsupported/missing/invalid/error/partial separately. All verified-data positive paths must pass before 24P.3 completes; rollout fallbacks are not a completion substitute.

#### 24P.4 - PLANNED - Interactive analytics charts

- Goal: implement the large Tender Activity grouped bar/area chart, multi-ring Company Fit distribution, Global Geography country/count/horizontal-bar panel, distinct industry/category/source breakdowns and deadline calendar heatmap with interactive shared filters, authorized Discover drilldowns, honest date-range semantics and no-data states.
- Affected files (future implementation): `app/api/saas_shell.py`, `app/api/static/premium.js`, `app/api/static/premium.css`; existing organization data route/schema only if the audited aggregate contract requires it; `tests/test_premium_ui.py` and focused dashboard JavaScript tests added during implementation.
- Dependencies: 24P.2 and 24P.3; timestamp and fit contracts from 24P.1.
- Acceptance criteria: chart/table/card populations reconcile; hover/focus details and legends declare counts, units, denominators and preliminary/full scoring distinctions; filters are keyboard usable and reset predictably; selected date field/window/timezone and unknown-date policy are visible. No history means no historical trend; unsupported classifications, unknown geography, missing deadlines and failed sources show honest explanatory states. Charts never create observations from absent data. Tender Activity buckets use an audited real timestamp and declared grouping; enable area presentation only when supported temporal observations exist, with gaps preserved and no invented interpolation. Geography shows readable country names and real counts; the deadline calendar uses real deadline dates and per-day counts, with missing deadlines separate. Each chart provides readable table/list alternatives and keyboard-operable drilldowns that preserve supported context and predicates or explain why unavailable.
- Tests: chart/table reconciliation against real-schema fixtures, date/range boundaries, unknown categories/countries/deadlines, no history, filter combinations, company switches and stale requests; keyboard/screen-reader alternatives, contrast/reduced motion and responsive browser inspection.


- **Expanded delivery gates (PLANNED):** after 24P.3.7-8, wire actual population contracts to publication/search time series, grouped bars and observed-only area series; implement canonical country distributions with multi-country/unknown accounting, disjoint preliminary fit rings, distinct industry/category hierarchy charts, source counts and normalized deadline heatmaps. All six KPI cards must consume the same contracts. Targets remain `saas_shell.py`, `premium.js`, `premium.css` and focused JS/UI fixtures; no additional schema migration for rendering. Chart selection emits population ID + canonical predicate + time semantics for 24P.5 replay. Acceptance: every chart bucket/segment equals its accessible table and authorized replay count on verified fixtures; fit shares sum to 100% of eligible scored U, unknown scores are shown separately; no interpolated observations across coverage gaps. Verify populated, zero, partial, missing and unsupported states per chart, not only empty-state screenshots. Country/category/industry widgets must work when supported enrichment exists; fallback explains missing evidence and known/unknown coverage during rollout. Keyboard focus/tooltip/legend and mobile table alternatives expose the same values.

#### 24P.5 - PLANNED - Opportunity, deadline and source-health widgets

- Goal: implement the professional sortable Top Opportunities table, upcoming-deadline, Source Health and Data Completeness widgets, plus compact contextual summaries and actionable business widgets from supported authorized data, with actions connected to existing tender detail, authorized Discover results, Saved and PDF assistant workflows.
- Affected files (future implementation): `app/api/saas_shell.py`, `app/api/static/premium.js`, `app/api/static/premium.css`; integration review of `app/api/static/discovery.js`, `app/api/static/saved.js`, `app/api/saved_ui.py`, `app/api/dashboard.py`; `tests/test_saved_ui_contract.py`, `tests/js/discovery.test.cjs`, `tests/test_organization_pdf_rag.py`, `tests/test_premium_ui.py`.
- Dependencies: 24P.3 data contract and 24P.4 filters; existing role-aware actions and PDF/Saved services.
- Acceptance criteria: recency uses a declared real timestamp; upcoming deadlines use valid dates and stated timezone/window; source health distinguishes success/partial/failure/unknown and latest-search scope from any available historical scope. Actions open the correct scoped record/workspace, preserve viewer restrictions and safe links, and honestly disable unavailable capabilities. Top Opportunities uses only available real tender metadata: title/identifier, source, buyer, country, industry/category, publication date, deadline, value/currency, preliminary fit and completeness where audited fields exist. Unavailable cells remain explicit; ranking uses a declared supported criterion, never an invented AI score. Sorting is deterministic, keyboard accessible, announces direction and handles unknown values consistently; filters, counts and table rows reconcile to the declared population. Data Completeness shows audited present/required metadata counts, unknown states and gaps without implying document acquisition or full analysis readiness. Contextual summaries reference real counts and dates; actions respect role permissions and unavailable capabilities. No fabricated alerts, save counts, revenue, savings or automatic document acquisition.
- Tests: table sorting/ties/unknown cells and supported ranking, table/filter/count reconciliation, completeness numerators/denominators and missing fields, summary accuracy, ordering/date boundaries, missing timestamps/deadlines, partial/total source failure, authorized Discover drilldowns and working navigation/actions, viewer mutation denial, scoped Saved/PDF regressions and workspace changes during requests.


- **Expanded delivery gates (PLANNED):** depends on 24P.3.8 and 24P.4 population/predicate handoff. Deliver server-consistent paged sortable Top Opportunities and shared source/country/industry/category, fit-band, publication/search range and deadline-window filters; use taxonomy IDs and exact normalized bounds, not labels or independent JS date parsing. Sort every supported column with null/nonfinite last in both directions, explicit currency grouping for values, then stable identity tie-break; preserve finite zeros and disclose historical/current fit stage. Targets: `premium.js`, `premium.css`, `saas_shell.py`, `discovery.js`, `history.js`, analytics routes/schemas and focused JS/API tests; no new migration for UI state. Deliver an explicit Discover report/replay import interface with epoch checks and immutable population/predicate descriptor, including bounded date and disjoint fit ranges plus country/taxonomy controls. Acceptance: each chart/KPI/table drilldown displays exactly the originating filtered identities and total across pages, preserves origin/profile/timezone and never triggers a new search to imitate the population; expired/unauthorized replay gives an honest reload/error state. Keep existing 24P.0 local Discover ownership/clear behavior and default discovery flow compatible.
- **Data-quality and action gate (PLANNED):** show per-field country/taxonomy/date/score coverage, invalid/ambiguous/unmapped counts, missing identities, deduplication conflicts, partial source/history coverage, actual last observation and ten-group completeness gaps. Links expose safe raw-value provenance where authorized. Source health includes latest search and explicitly observed historical samples, not uptime. Country/category/date/fit cells render enriched verified values rather than remaining permanently unavailable. Detail/official-link/Saved/PDF actions resolve correct organization/company and document/score stage; backend enforces existing write-role restrictions and viewer has read navigation only. Do not conflate existing viewer discovery/enqueue contracts with newly authorized mutations. Company-scoped PDF fit requires verified 24P.3.8 bindings; old organization records remain labeled as such. Acceptance: totals and quality counts reconcile to U; no save/PDF operation runs during render; owner/admin/member actions and viewer denial pass existing scoped workflows without regressions.

#### 24P.6 - PLANNED - End-to-end acceptance and real-browser validation

- Goal: complete security, regression, accessibility, performance and real-browser desktop/tablet/mobile acceptance before claiming premium visual readiness.
- Affected files (future fixes only when findings justify them): Phase 24P UI/API files listed above and relevant `tests/test_web_auth.py`, `tests/test_premium_ui.py`, `tests/test_saas_core.py`, organization/discovery history/Saved/PDF tests, JavaScript regressions; evidence and status in `PHASE24_PROGRESS.md`.
- Dependencies: 24P.0 through 24P.5 completed and supported data contracts verified; an available real browser. Prior Phase 24S.2B.4 remains completed and must not be weakened or relabeled.
- Acceptance criteria: no confirmed unresolved security findings in changed scope; existing auth/tenant/company/viewer boundaries, stale guards, API compatibility, Saved, PDF and source failures pass regression. Real browser checks cover landing/auth/shell/Overview V2/Discover/company/PDF plus the approved rich command center at desktop/tablet/mobile widths, including all six KPIs, varied charts/widgets, sortable opportunities and filter/drilldown flows; keyboard navigation, focus, accessible chart alternatives and honest states pass. Measure actual render/update latency, payload size and layout behavior against a documented representative dataset and baseline; no unsupported performance claims. Record browser/tool limitations honestly; visual acceptance stays pending until checks run.
- Tests: targeted Python/JavaScript regression and relevant full offline suite; tenant/role/race/security cases; keyboard/accessibility checks and measured performance; real-browser responsive end-to-end flows for successful, empty, unavailable, partial/error and no-company states; `git diff --check`. Record actual outcomes without recycling older runs as Phase 24P evidence.


- **Missing-capability regression matrix (PLANNED):** 24P.6 depends on every 24P.3 checkpoint and populated 24P.4/5 flows, not just graceful unavailable rendering. Add focused `tests/test_analytics_normalization.py`, `tests/test_analytics_aggregates.py`, `tests/test_analytics_api.py` and `tests/js/premium.test.cjs` (proposed files), extending existing source, history API/repository, preview/full-AI, scoring-run, source-health, organization, Saved/PDF and `tests/js/discovery.test.cjs` regressions. For each country, category, industry, fit, history, publication/deadline, completeness and source-health capability, require positive verified-data plus missing/invalid/unsupported/partial/error fixtures. Test raw/provenance preservation, no currency/source country inference, invalid taxonomy/crosswalks, historical-vs-current digest, full/preliminary separation, zero/null/nonfinite and every band endpoint. Assert known/unknown/excluded denominators, duplicate identities/conflicting payloads and chart/table/replay equality.
- **Security/history/date/compatibility gate (PLANNED):** require unauthenticated, outsider, owner/admin/member/viewer, revoked membership, same-tenant other-company and cross-tenant tests for all new routes, paging and replay; forged/expired cursors, cache separation, profile/epoch races and read-no-mutation assertions. Retrieve >100 events and multi-page rows/runs with timestamp ties and concurrent inserts under a fixed watermark; prove no skip/repeat and cap/partial disclosures. Test `[start,end)` at exact endpoints/fractional seconds, date-only versus instant, UTC offsets/DST/leap days, expired deadlines and unknown timezone. Test optional migrations against old DB fixtures and legacy JSON/API consumers, existing 24P.0 filter ownership, Saved/PDF/auth and source-failure behavior. Acceptance: all new focused tests and relevant offline regression suite pass with actual recorded results; zero unresolved isolation/authorization or count-reconciliation defects.
- **Measured browser/product gate (PLANNED):** validate at 1440px desktop, 768px tablet and 390px mobile (plus narrow overflow checks), populated verified fixtures with >100 search events, multiple countries/taxonomies and paged opportunities, as well as empty/unknown/partial/error/no-company states. Exercise all six KPIs, chart focus/selection, every shared filter, sorting/pagination, historical replay, company switches and role-aware actions. Acceptance: no unintended page overflow or clipped controls, accessible table alternatives and visible keyboard focus, no console errors, no stale-company rows/counts, and all drilldowns reconcile exactly. Record dataset size, hardware/browser, API latency, payload bytes and render/update latency; set numeric budgets before measurement, investigate regressions above 20% versus the recorded same-fixture baseline rather than claiming performance from unrun checks. Retain browser evidence and limitations; `git diff --check` must pass. Completion requires implemented working positive paths for every missing premium capability when verified data exists; genuinely unsupported records retain truthful fallbacks without blocking supported records.

### Exact next single implementation task

24P.0 and the evidence-based 24P.1 audit remain completed. The authorized 24P.2 presentation implementation is delivered below. Close its remaining real-browser acceptance gate when a browser is available; do not label visual readiness or 24P.2 COMPLETE before that gate is verified. 24P.3-24P.6 and every expanded 24P.3.1-24P.3.9 checkpoint remain PLANNED. No later-phase aggregation, enrichment, chart interaction, sorting/replay, API or migration has been implemented here.

PRODUCTION_TOUCHED=False

## Phase 24P.2 verified implementation results (2026-10-10)

Status: **IMPLEMENTED; required browser acceptance BLOCKED**. All available code/runtime checks below passed. This checkpoint is deliberately not labeled COMPLETE because its desktop/tablet/mobile real-browser layout and keyboard acceptance checks could not run. No visual readiness, screenshot match or deployment readiness is claimed.

### Delivered presentation and scope

- Read the approved rich first-reference specification, complete 24P.1 population/metric audit, architecture, existing shell lifecycle, Discover report ownership and regression contracts before edits. Preserved the user's pre-existing progress-document changes and did not modify any existing `.tmp-phase24` directories.
- Added `app/api/command_center_ui.py` as static semantic presentation, integrated into the existing Overview through `saas_shell.py`. Preserved the compact sidebar, organization selector, active-company topbar, existing onboarding and supported navigation.
- Added layered navy/indigo/violet surfaces, six individually labeled KPI cards, asymmetric activity/fit/geography/deadline panels, distinct industry/category/source containers, Source Health, Data Completeness and Top Opportunities. Existing source reports and Discover links remain working navigation. Chart filters, chart marks, ranking and sorting are not presented as functional.
- Every analytics KPI stays unavailable until 24P.3 provides a verified contract. Explicit reasons identify deduplication, eligibility, absent High Fit threshold, source observations, absent tender countries and pending deadline normalization. No aggregate, timestamp, country, classification, threshold, tender value or history is invented. Population/date-range unavailability is visible; organization/company labels come from current workspace context and use textContent.
- Preserved existing browser-report counters under a keyboard-operable operational disclosure: returned rows, rows with preliminary fit, attempted sources and local receipt time. These remain distinct from unique procurement analytics and historical activity, with their existing event owners and reset behavior.
- Added context-only loading/error/no-company/unavailable handling and accessible busy/status announcements. The new dashboard script performs no fetch, source search, save, PDF operation or other mutation. Workspace switches replace context labels and never retain analytical values.
- Added desktop six-card layout, intermediate three-card layout, tablet two-column panels, mobile stacked panels/two-card layout and single-card narrow layout. Used intrinsic minmax sizing, wrapped headings, local typography, visible focus, reduced motion and 44px navigation/action targets. Retained existing Escape/focus-restoration navigation behavior. Theme activation follows Overview navigation only, preserving other workspaces' existing presentation.
- Updated cache versions for the modified shell/premium assets, navigation regression DOM fixtures and targeted presentation/state tests. No backend, authorization, API, Saved/PDF/Discover implementation, database or tenant isolation contract changed.

### Actual verification

- Existing local portable Node **v24.21.0** reused; no installation, package fetch or external request. Syntax checks passed for all **7** application JavaScript assets and **6** JavaScript regression files.
- All **6** JavaScript regressions passed, exit 0: company profile preservation/viewer guard; Discover rendering/filter ownership/partial failures/repeatability/stale requests; full-AI rendering; all existing navigation/command destinations and shortlist failures (also checks Overview-only theme activation); shortlist rendering; new premium context/loading/error/no-company/scope replacement tests. Final modified navigation and premium-state regressions were rerun after routine fixes.
- Broad relevant offline Python regression across **33 files**: **283 passed, 1 skipped, 390 subtests passed**, exit 0. Covers authentication, organization/company/tenant restrictions, Saved/shortlist, PDF/RAG, search history, source health, discovery and UI contracts. The skip is the existing Windows symlink privilege limitation; one existing Starlette deprecation warning. Used a new `.cache/phase24p2` launcher/temp tree, with external socket connections forbidden and numeric loopback allowed for local asyncio fixtures.
- Final targeted rerun after presentation/cache-contract changes: **82 passed**, exit 0, one existing Starlette warning. Includes premium, shell, responsive, navigation audit, Saved, full-AI, web auth, source-health and history UI contracts. No test skips in this final selection.
- Initial Python launcher collection failed because repository root was absent from sys.path; fixed the launcher and reran successfully. A JS navigation mock initially lacked document.body; expanded the mock and added actual theme-scope assertions. A final cache-version test expected the old shell version; updated its expected changed-asset versions and reran all 82 checks successfully. These were resolved verification harness/contracts, not outstanding product defects.
- Browser capability inspection through computer-use returned no available browsers/apps. Attempt to create a localhost tab in the in-app browser returned **Browser is not available: iab**. No browser page, screenshot, responsive geometry, contrast rendering or physical keyboard workflow was verified. No server or production service was started for this failed capability probe.
- Final changed-Python compilation: PASS. Final syntax checks and all six JavaScript regressions rerun: PASS, exit 0. Final `git diff --check`: PASS, exit 0 (Git reports only existing LF-to-CRLF normalization notices). Static cascade review corrected inherited light-theme command-menu and onboarding text colors; the final 82-test UI selection passed again after those CSS adjustments.

### Remaining acceptance blocker

A real browser is required to verify the rendered dashboard at representative desktop/tablet/mobile widths, narrow overflow, visible focus, keyboard navigation, native disclosure and no-company/error/loading presentation. The tool capability failure prevents that check in this session. Continue from this implementation when a browser becomes available; do not install dependencies or relax the no-network constraint to bypass the blocker. All expanded 24P.3.1-24P.3.9 roadmap content is preserved verbatim.

PRODUCTION_TOUCHED=False

## Phase 24P.3.1-3 autonomous foundation results (2026-10-10)

This execution record supersedes the earlier PLANNED references only for work
explicitly described here. The preceding roadmap and pre-existing 24P.1/24P.2
changes are preserved. Phase 24P.2 browser acceptance remains **PENDING**.

| Subcheckpoint | Verified status |
| --- | --- |
| 24P.3.1 | **COMPLETE for the fixture-supported enrichment foundation.** All ten existing adapters retain selected country/category/date evidence in an additive versioned contract; unsupported fields remain missing/unsupported. No new source field request or migration. |
| 24P.3.2 | **Normalization implemented and verified.** ISO alpha-2 codes plus explicitly limited name/alpha-3 aliases, location semantics, conflicts, ambiguous/invalid/missing values, multi-country and deduplication are tested. The full roadmap acceptance wording about KPI/distribution/equality filters is **not marked COMPLETE**: those consumers require later population/chart/filter checkpoints, which were not started. |
| 24P.3.3 | **PARTIAL; offline CPV label registry verified 2026-10-11.** Supplied TED CPV 2008 HTML has 9,454 unique eight-digit labels and a pinned SHA256. Parent edges, check-digit semantics, obsolete history, actual TED CPV JSON fields and industry crosswalk are not evidenced. Completion acceptance remains blocked; independent AusTender/ZA classifications are preserved. |

### Delivered evidence and preservation

- Added `docs/PHASE24P3_ENRICHMENT.md`: adapter-by-adapter support register, exact
  field paths, fixture references, versions, country/location semantics, supported
  source-category registry, raw/extracted-date limitations and remaining blockers.
- Added optional `TenderNotice.enrichment`, validated schema-1 API enrichment,
  source/external identity checks, normalizer/adapter versions, real UTC parser
  observation, existing connector version on new opportunity writes, raw values and
  field paths. No entire upstream bodies or credentials are copied. Source notice
  scoring provenance explicitly remains unavailable; preview/full-AI fields are
  unchanged. Publication, observation, release/update and storage time are distinct.
- New Discover, persisted discovery history, existing Saved snapshots and shared
  opportunities carry enrichment. Old JSON decodes with null enrichment and is not
  backfilled or rewritten. Metadata does not enter existing keyword search matching.
  Original identity and dataclass equality/hash behavior are preserved.
- SAM.gov fixture-backed place-of-performance code/name establishes US; conflicting
  code/name clears canonical countries. Region, buyer address, currency, source and
  configured coverage never establish country. Other adapters remain missing country
  evidence. Multi-location/invalid/ambiguous variants are explicit contract tests,
  not claims of additional live source support.
- Categories use only explicit source fields and the two observed code/label pairs,
  with raw entries, reported role, conflicts and unique memberships. Unsupported CPV,
  arbitrary text and unverified codes produce no canonical category or industry.
- Date provenance preserves original JSON/CSV/XML scalars where available and labels
  extracted HTML/description/cell text. AusTender retains the selected decoded
  timezone-link parameter and display text; EIS updated fallback and UK release date
  are explicitly distinguished from publication semantics. Existing date values and
  parsing behavior remain intact. No 24P.3.6 parser/window implementation was added.
- Authentication, configured connector credentials, source requests, role/company/org
  checks and dashboard behavior are unchanged. Added authorized owner discovery,
  history and Saved roundtrips, read-no-refetch checks, viewer Saved-write denial and
  outsider/anonymous denial. Existing broader tenant/company/Saved/PDF/login/security
  tests remain in the regression selection.
- Did not edit `command_center_ui.py`, shell/premium assets or pre-existing UI tests.
  Existing `.tmp-phase24` directories were not accessed or modified. No external
  network, secret/.env read, dependency install, production action, commit, push or
  deployment. No 24P.3.4-24P.6 implementation, aggregate, KPI or chart/filter acceptance
  is claimed.

### Actual verification

- Initial focused adapter/contract/connector/workflow selection: **149 passed**, exit 0.
- Additional adapter/source/normalization selection: **126 passed**, exit 0.
- Final normalization/model compatibility checks: **54 passed, 15 subtests passed**,
  exit 0. Added a hash/equality regression after review.
- Expanded offline regression across **46 files**: **509 passed, 1 skipped,
  1 deselected, 390 subtests passed**, exit 0. The skip is the existing Windows symlink
  privilege limitation. The deselected test is `RagConfigTests.test_semantic_defaults`,
  which creates/reads a `.env` fixture; it was excluded to obey the no-.env constraint.
  This is a broad relevant selection, not a claim that the entire repository suite ran.
- First broad attempt: 509 passed, 1 skipped, 1 failed because the launcher audit
  guard rejected that RAG test's attempted `.env` creation before opening the file.
  No .env was read. The final selection excludes only that test and preserves the
  guard; no product change or relaxed secret policy was used to bypass it.
- Final date-provenance review fixes were verified separately after the broad run
  started: **58 passed**, exit 0. Covers empty publication/update fallback, selected
  AusTender raw deadline, EIS/UK adapters and enrichment/auth/history/Saved contracts.
  The broad run therefore is supplemented by this final changed-scope verification.
- Existing local Node **v24.21.0**: syntax checks for all application JS assets and
  six JS regression files passed. All **6** JS regressions passed, exit 0: company,
  Discover, full-AI, navigation, premium states and shortlist. The initial command
  omitted the required dashboard fixture argument; corrected it and reran all six.
- Changed Python compilation: PASS. `git diff --check`: PASS. Reviewed modified source,
  API integration and every new analytics/schema/test/document file. Existing
  Starlette deprecation warning and Git LF/CRLF normalization notices remain.
- Python launcher/temp artifacts are isolated under new `.cache/phase24p3`, with
  external socket connections rejected, numeric loopback allowed for local fixtures,
  and an audit guard prohibiting .env file access.

### Precise remaining work

To complete 24P.3.3, supply fixture-verified actual TED classification fields,
authoritative hierarchy evidence and any required obsolete/check-digit reference.
NACE mapping remains unsupported without a verified crosswalk; real chart/filter
acceptance is deferred to later authorized checkpoints. The supplied offline
CPV 2008 label reference is now verified; see the continuation audit below.
To close the full 24P.3.2 downstream acceptance wording, future authorized checkpoints
must verify KPI/distribution/equality-filter agreement over their shared population.
Neither absence was replaced with fabricated success. 24P.2 browser acceptance remains
pending; 24P.3.4-24P.6 remain unstarted in this batch.

PRODUCTION_TOUCHED=False

## Phase 24P.3.3 continuation - 2026-10-11 - PARTIAL

Only 24P.3.3 was continued. Added the inert offline CPV 2008 registry (9,454 labels),
exact code validation, explicit unsupported parent/check-digit lookup semantics,
versioned classification normalization and legacy-policy compatibility. Raw values,
provenance, multiple codes, deduplication, unknown/conflicting entries and independent
AusTender/ZA IDs are retained. Reference SHA256:
`e4134a747acbc18d99a778412002caf55212baf8cbc1c695a03fab00edecbbb9`.
Full coverage verification command and precise blockers are in
`docs/PHASE24P3_ENRICHMENT.md`. No TED fields were guessed or newly requested.
No unsupported NACE mapping, hierarchy edges or obsolete/check-digit algorithm.

Focused checks: 72 passed before the additional company-isolation assertion;
30 enrichment tests passed after that assertion. All six JavaScript suites passed using the existing local Node runtime.
The final CPV-specific suite passed 19 tests; counts above overlap.
Broad offline regression results are recorded below. The dotenv guard rejected
tests that require dotenv access; those tests were excluded, never bypassed.
A stale Monitoring asset-version assertion and a Windows monotonic-clock test
flake were repaired in tests only. The HTTP/transport rerun passed 424 tests
with 2 existing raw-deflate skips; application HTTP/PDF code was unchanged.
24P.3.3 is not marked complete. 24P.2 real-browser acceptance remains pending.
24P.3.4-24P.6 were not started. No network, secrets, installation, production,
migration, git add/commit/push/deploy or modification of `.tmp-phase24*` directories.

PRODUCTION_TOUCHED=False

Final permitted full offline regression (2026-10-11): **1,836 passed, 3 skipped,
37 deselected, 440 subtests passed**, one existing Starlette deprecation warning,
exit code 0. Command: `python .cache/phase24p3/run_tests.py cpv-regression-verified
tests -k "not dotenv and not public_environment_example_is_trackable_but_real_file_is_not
and not semantic_defaults"`. The 37 deselections are explicit exclusions of
dotenv-named tests plus the environment-example reader and synthetic dotenv writer;
they are not counted as passing. Skips: Windows symlink privilege unavailable (1),
raw deflate without checksum (2). External-connect and dotenv-open guards remained
active. All six JavaScript suites passed. Final `git diff --check`: PASS.
This is offline regression evidence, not live-source or real-browser acceptance.
24P.3.3 remains PARTIAL for the documented reference/source/hierarchy blockers.


## Phase 24P.3.3 official offline completion audit ? 2026-10-11 ? PARTIAL

Verified the supplied OP-TED/eForms-SDK 1.15.1 Genericode (CPV Version 2008):
9,454 IDs, 9,447 exact matching labels, 7 apostrophe differences; 9,409 explicit
edges, 45 omitted parents, no orphans/cycles. Packaged 9,400 verified edges;
9 incident to label mismatches are withheld. Added tested explicit parent,
ancestor, descendant and tri-state category matching without prefix inference.
Missing parents remain unknown. Original labels, taxonomy versions and stored
normalization/snapshots are preserved.

Official TED field-list names, aliases and Procedure/Part/Lot references are
verified and captured as documentation-row evidence. JSON response types,
CPV scheme discrimination and part/lot binding are absent from supplied evidence;
TED extraction remains pending, with no guessed positive response fixture or
new request fields. Check digits and CPV-to-NACE remain unsupported.
All source URLs, versions, SHA256 values, exact mismatch/coverage rules and the
next evidenced step are in `docs/PHASE24P3_ENRICHMENT.md` completion audit.
24P.3.3 fails the full response-schema acceptance gate and remains PARTIAL.
24P.2 browser acceptance remains PENDING; 24P.3.4+ unstarted.
Existing uncommitted work retained; no network/secrets/install/production,
migration/commit/push/deploy or `.tmp-phase24*` changes.

PRODUCTION_TOUCHED=False


Final audit regression: **291 passed, 390 subtests passed**, exit 0; one existing
Starlette warning. Explicit broad 32-file offline selection covers Discover,
Saved, PDF, auth/permissions, tenant/company isolation and 24P.2 UI. No -k,
deselections, skips or unrelated test repairs. Not a full-repository run.
Exact command, overlapping focused results and initial new-test expectation
corrections are recorded in the enrichment document. All six JS suites passed
with existing Node. Changed Python compileall and final `git diff --check`: PASS.
24P.3.3 remains PARTIAL because actual TED classification response types and
context/scheme binding require offline official schema/capture evidence.


## 24P.3.3 public TED v3 evidence integration - 2026-10-11 - PARTIAL

Both supplied YAML/response SHA256 values verified. The real public search request
returns three 2016 notices with nonempty classification-cpv array<string>; all nine
values match the existing CPV 2008 registry (five unique codes). None of the six
requested main/additional proc/part/lot fields is returned. OpenAPI verifies their
array<string> descriptions only; the sample contains no code-to-entity binding or
roles. Aggregate ingestion into existing notice-level memberships would collapse
lot evidence, so no guessed parser or request fields were added. Existing adapters,
9454-code registry, verified/withheld hierarchy, schemes and snapshots are preserved.

Added a pinned offline evidence verifier, minimal sanitized real sample and positive/
negative tests, including real-sample Discover/history/Saved authorization, tenant/
company isolation and no refetch. See the public TED v3 capture audit in
`docs/PHASE24P3_ENRICHMENT.md` for exact values, nested types, source hashes and a
minimal future evidence-capture proposal. Scope/role ingestion remains blocked:
24P.3.3 is PARTIAL, 24P.2 browser acceptance is PENDING, 24P.3.4+ is unstarted.
No network, .env/secrets, package installation, production, migration, staging,
commit/push/deploy or changes to existing .tmp-phase24 directories.


### Public-capture audit validation

Focused guarded offline run: **80 passed**, exit 0 (five files: new
`test_ted_api_evidence.py`, TED source, CPV registry, CPV hierarchy, analytics
normalization). Broad guarded offline run: **306 passed, 390 subtests passed**,
exit 0; 33 selected files, the earlier completion-audit 32-file command plus
`tests/test_ted_api_evidence.py`, using new basetemp
`.cache/phase24p3/p33-ted-evidence-broad-final`. No skips/deselections; one existing
Starlette deprecation warning. Counts overlap. External-connect and dotenv-open
guards remained active. This is a relevant broad regression, not a full-repository
or browser run. Six local JavaScript suites passed (company, discovery,
discovery_full_ai, phase24r, premium, shortlist_ui) using the existing local Node
and `.cache/phase24p33-completion/dashboard.html`. Compileall for sources/analytics
and both new Python files passed. The initial new fixture had a PowerShell UTF-8
BOM, causing four new-test failures; regenerated as UTF-8 without BOM and reran
successfully. No existing regression expectations were changed.

Final new-test rerun after adding the five-unique-code assertion and exercising the
original response including links: **15 passed**, exit 0. Compileall and final
`git diff --check`: PASS. Reviewed all 20 untracked source/doc/test files under
app/scripts/tests/docs for trailing whitespace and merge markers: none found.
Pre-existing .tmp-phase24 directories were excluded and preserved.

## 24P.3.3 official eForms XML context integration - 2026-10-11 - PARTIAL

Implemented separate offline `app/analytics/eforms_xml.py`: bounded UTF-8 XML-only
classification extraction on documented procedure/lot/part paths; group identifiers
retained separately without inventing group classification/composition. Exact CPV
strings are checked against pinned CPV 2008; raw technical/procedure/internal IDs,
main/additional roles, namespace-expanded indexed field locations, versions and
provenance/checksums are retained. No notice/company membership flattening.
Fail-closed DTD/entity, namespace, size/depth/node, malformed XML, duplicate ID,
unknown code/scheme/path and explicit unsupported CPV-version checks are covered.

Official SDK fixture is byte-identical and labeled sdk_example, not published XML.
Separate synthetic multi-lot/role/group/part and security cases are labeled as tests.
Existing TED Search connector supplies JSON only, no already acquired XML bytes;
optional live integration would require extra acquisition and remains unwired.
Default TED_FIELDS, requests, adapters, enrichment and stored snapshots unchanged;
Search CPV arrays stay aggregated/unbound. No live lot extraction is claimed.
Exact evidence hashes, documentation 1.15 versus XML SDK 1.16, scope limits and
future published-notice identity/storage/authorization acceptance are recorded in
`docs/PHASE24P3_ENRICHMENT.md` XML context section.

Validation: focused guarded offline 107 passed; broad guarded offline 473 passed,
390 subtests, exit 0, 40 selected files, one existing Starlette warning, no skips
or deselections. Final explicit old-CPV-version rejection then verified with 28
XML tests passed. Counts overlap; broad run predates that final narrow addition.
All six existing local JS suites passed. Python compileall and git diff --check
passed; authored new files have no trailing whitespace/merge markers. Official
fixture deliberately retains the source's trailing comment whitespace and checksum.
Prior tracked app/tests diff verified unchanged against the start-of-task copy.

24P.3.3 remains PARTIAL: SDK XML does not verify actual published-notice acquisition
or Search identity binding, and Part-bearing real notice roots remain unsupported.
24P.2 browser acceptance remains PENDING; 24P.3.4+ unstarted. No network, .env/secrets,
installs, migrations, production, staging/commit/push/deploy or .tmp-phase24 changes.

PRODUCTION_TOUCHED=False

## 24P.3.4 - COMPLETE - preliminary fit contract (2026-10-11)

This execution record supersedes earlier unstarted/PLANNED references ONLY for
24P.3.4. Preserved the existing audit, enrichment work and all pre-existing
tracked/untracked changes. No existing .tmp-phase24 directory was altered.

Implemented:

- `app/analytics/fit.py`: pure reusable classification/eligibility under immutable
  `preliminary-fit-v1`, raw score preservation, finite strict int/float 0..90,
  Low [0,35), Medium [35,65), High [65,90], Matched >=35, High Fit >=65 with one
  eligible denominator. Unknown includes missing/malformed/bool/nonfinite/range,
  untrusted origin, unknown/mixed stages, scope/version conflicts and stale digest.
- Current fit requires verified server-origin evidence, exact organization/company
  binding and current canonical profile digest equality. Legacy explicitly staged
  trusted history may show only historical preview at search time. Schema defaults
  cannot manufacture historical stage evidence. Saved client evidence is not trusted.
- Additive frozen preliminary_provenance on new authorized Discover items, retained
  in future H and Saved serialization: actual UTC calculation time, scope IDs,
  reused scoring.runs.profile_digest, `metadata-preview-v2` and policy/stage version.
  Existing preview formula unchanged; raw scores are not rescaled. Stop factors
  remain separately presented reasons. Full-document score 0..100 remains separate.
- `docs/PHASE24P3_ENRICHMENT.md` records verified formula/digest infrastructure,
  authorization/trust prerequisites, serialization, historical provenance gaps and
  unchanged R/P/opportunity contracts. No timestamp/digest/identity is backfilled.
- Focused tests cover all requested boundaries and malformed inputs, version/stage
  conflicts, digest determinism/changes/missing/stale, legacy decode, full-score and
  stop-factor separation, owner/member/viewer reads, outsider/anonymous rejection,
  switched-company and cross-tenant isolation, identical profiles across companies,
  stable repeated reads and unchanged stored evidence after profile edits.

Not implemented in this checkpoint: analytics GET/API/populations, aggregates,
KPI/chart/table/filter wiring, paging, rescore, jobs, migrations or browser acceptance.
The reusable policy is the single contract for those later consumers. Viewer access
and existing viewer-triggered discovery-history persistence semantics are unchanged.

Validation (counts overlap; do not add):

- Guarded targeted Python: **91 passed**, exit **0**; command
  `python .cache/phase24p3/run_tests.py p34-focused-final tests/test_analytics_fit.py
  tests/test_discovery_preview_scoring.py tests/test_discovery_full_ai_contract.py
  tests/test_discovery_history_api_behavior.py tests/test_scoring_workers.py`.
- Guarded broad Python: **567 passed, 390 subtests passed**, exit **0**, 200.84s,
  44 files, no skips/deselections. Selection is the exact 40-file XML context broad
  command documented in the enrichment file plus test_analytics_fit.py,
  test_scoring_workers.py, test_scoring.py and test_discovery_history_repository.py;
  basetemp `.cache/phase24p3/p34-broad`. One existing Starlette deprecation warning.
- Final narrow run after additional missing/trust/cross-tenant assertions:
  **38 passed**, exit **0**; `python .cache/phase24p3/run_tests.py
  p34-isolation-final tests/test_analytics_fit.py`. Broad run predates these final
  assertions; the final narrow run verifies them. Initial focused run had 48 passes
  and one new-test fixture failure because duplicate company names are forbidden;
  fixed that fixture to use separate workspace names with identical profile JSON.
  No unrelated tests/assertions were changed or weakened.
- All six local JS suites passed, each exit **0**: company, discovery,
  discovery_full_ai, phase24r, premium, shortlist_ui. Existing local portable Node
  and `.cache/phase24p33-completion/dashboard.html` reused; no installation.
- Changed Python compileall: exit **0**. `git diff --check`: exit **0**.
  Simple sanity review of **24 untracked source/doc/test files** under
  app/tests/scripts/docs: Python AST parses, no merge markers/trailing whitespace.
  XML fixtures retain original bytes; existing temp directories were excluded.

24P.3.4 is COMPLETE for this authorized contract checkpoint. 24P.3.3 remains
PARTIAL: actual published XML integration blocked. 24P.3.2 downstream consumer
verification remains pending. 24P.2 browser acceptance remains PENDING.
24P.3.5 onward remains PLANNED at the 24P.3.4 closure (superseded below). No browser/deployment claim, network, secrets/env
access, package download, production, staging/commit/push/deploy or migration.

PRODUCTION_TOUCHED=False

## 24P.3.5 — 2026-10-11 — PARTIAL

Implemented additive company-scoped history-page and history-snapshots GETs,
signed account/scope/query cursors, frozen ID/as-of watermark, deterministic
created_at/id keyset, UTC [start,end) filters, observed counts and explicit
snapshot/error states. New R list uses a frozen bounded run-ID manifest; revision
reads retrieve immutable stored bodies by snapshot/ordinal/revision with calculation
provenance and explicit 500-candidate cap. Legacy routes/defaults and 24P.3.4 fit
policy/provenance are unchanged. No H/Discover/R identity-only joins or GET writes.

Audit, API contracts and exact blockers: [retrieval register](docs/PHASE24P35_RETRIEVAL.md).
COMPLETE is withheld: R populations above 1000 explicitly fail rather than truncate;
deleted H bodies cannot be recovered and storage does not enforce immutability;
legacy UI remains limited; noncanonical imported timestamp/byte-bound/PostgreSQL
runtime acceptance is not demonstrated. Lifetime totals are never claimed.

Guarded offline broad p35-broad: **395 passed, 390 subtests passed**, exit 0,
237.88s, 34 selected files. Final focused p35-final-focused: **96 passed**, exit 0.
Final acceptance p35-acceptance-final: **8 passed**, exit 0, covering 123 events,
equal timestamps, concurrent backdated inserts, UTC boundaries, deleted/corrupt
snapshots, scoped immutable R revisions, roles, anonymous/outsider, switched
company, tampered/expired/replayed cursors and revoked membership. Counts overlap.
Broad predates final narrow assertions and small completeness/error refinements;
the final narrow runs validate those changes. One existing Starlette warning.
Final p35-final-scoring: **50 passed**, exit 0, 24.56s. Initial p35-focused:
53 passed; p35-manifest-final: 8 passed (also overlapping, all exit 0).
Six existing local JS suites passed: company, discovery, discovery_full_ai,
phase24r, premium, shortlist_ui. Changed Python compileall and git diff --check pass.

24P.2 browser acceptance remains PENDING; 24P.3.3 remains PARTIAL;
24P.3.6+ not begun. Next checkpoint: close 24P.3.5 blockers before starting 24P.3.6.
Branch phase24-professional-saas-core, HEAD 93f02eb38b6570977248af10f4dcb01b4809f8fc
remain unchanged. Existing uncommitted files and .tmp-phase24 directories preserved.
No secrets/config reads, network, installs, real-data migrations, production,
staging, commit, push or deploy. PRODUCTION_TOUCHED=False.

## 24P.3.6 - 2026-10-11 - COMPLETE for the tested local contract

The earlier planned/not-begun status is superseded ONLY for 24P.3.6.
**PASS / local COMPLETE:** versioned deterministic source-date-v1, distinct typed
UTC instant/calendar date, retained exact raw/path/source evidence and precision,
explicit quality/unavailable reasons; additive normalized sidecars for new adapter
output, validated against retained evidence. No legacy snapshot reinterpretation.
Source-specific format/timezone audit and remaining capabilities are documented in
[date contract](docs/PHASE24P36_DATES.md). Original deadlines/published_at, observation
times, scores, snapshots, Saved/PDF, auth/cursors and storage semantics are preserved.

Pure deadline-window-v1 accepts one explicit server as_of, W=7 by default and
integer bounds 1..366. Instants use UTC [as_of,as_of+W days); date-only uses a
distinct W-calendar-day interval in supplied verified IANA display timezone.
Unknown zone/data is unavailable, never an invented offset/closing time. Request
timezone stays separate. DST/local midnight, exact end, expired, ambiguous and
invalid cases reconcile. Same selected scoped population and identity predicates
serve grouping and Discover-style replay; duplicates count once, conflicts are
excluded explicitly, and missing date-cell capability exposes unbucketed reasons.
Scope integrity checks do not replace API membership/company authorization.

**Downstream acceptance PENDING:** actual aggregate API, historical union, charts
and Discover UI wiring belong to 24P.3.7/3.8/4 and were NOT started. This checkpoint
does not close 24P.3.5 PARTIAL storage/retention/paging limitations. 24P.3.3 remains
**PARTIAL**, 24P.2 real-browser acceptance remains **PENDING**. No complete-market,
lifetime-history, source-sync-from-parser-time or full-AI-from-preview claim.

Guarded offline validation (overlapping selections, do not add counts):

- Broad **758 passed + 390 subtests**, exit **0**, 187.18s, 48 selected files,
  no skips/deselections. Exact command:

```powershell
python .cache/phase24p3/run_tests.py p36-broad tests/test_analytics_dates.py tests/test_analytics_normalization.py tests/test_analytics_fit.py tests/test_company_history_paging.py tests/test_eforms_xml.py tests/test_ted_api_evidence.py tests/test_cpv_registry.py tests/test_cpv_hierarchy.py tests/test_ted_source.py tests/test_organization_workflows.py tests/test_organization_pdf_rag.py tests/test_pdf.py tests/test_company_profile_pdf.py tests/test_web_auth.py tests/test_auth_api.py tests/test_session_access.py tests/test_organization_api.py tests/test_organization_data.py tests/test_shortlist_api_behavior.py tests/test_shortlist_api_contract.py tests/test_shortlist_integration.py tests/test_shortlist_repository.py tests/test_saved_ui_contract.py tests/test_discovery_history_api_behavior.py tests/test_discovery_history_api_contract.py tests/test_discovery_history_repository.py tests/test_discovery_preview_scoring.py tests/test_discovery_full_ai_contract.py tests/test_saas_core.py tests/test_premium_ui.py tests/test_phase24r_ui_audit.py tests/test_monitoring_ui_contract.py tests/test_responsive_ui.py tests/test_source_framework.py tests/test_austender_source.py tests/test_sam_gov_source.py tests/test_uk_fts_source.py tests/test_za_etenders_source.py tests/test_canada_buys_source.py tests/test_nz_gets_source.py tests/test_connector_workers.py tests/test_india_cppp_source.py tests/test_kz_goszakup_source.py tests/test_eis_business_metadata.py tests/test_scoring_workers.py tests/test_scoring.py tests/test_monitoring.py tests/test_source_http_transport.py
```

- Final **216 passed**, exit **0**, 24.17s; no skips/deselections:

```powershell
python .cache/phase24p3/run_tests.py p36-publication-final tests/test_analytics_dates.py tests/test_analytics_normalization.py tests/test_company_history_paging.py tests/test_discovery_history_api_behavior.py tests/test_shortlist_api_behavior.py tests/test_connector_workers.py
```

The broad run precedes the final additional date cases and narrow policy refinements
(strict source formats/minus-zero RSS, explicit display overflow/unbucketed,
immutable population inputs, unknown future policy retention and EIS's actual
lowercase pubdate evidence path). The final 216
selection tests all those refinements plus storage/API/worker compatibility.
Existing single Starlette deprecation warning; no test skips to hide defects.

Earlier focused commands: `python .cache/phase24p3/run_tests.py <run-name>
tests/test_analytics_dates.py tests/test_analytics_normalization.py
tests/test_company_history_paging.py` with p36-focused-final **124 passed**,
p36-final-contract **133 passed**, p36-final-evidence **137 passed**, each exit 0.
Initial p36-focused had **123 passed, 1 failed** from a new test importing the
fixture as RSS_SAMPLE instead of its actual RSS name; corrected the import without
changing existing tests/assertions. p36-acceptance-final used the exact final
six-file command above with that run name: **216 passed**, exit 0, 23.78s.
p36-policy-final used the same six-file selection: **216 passed**, exit 0, 23.91s.
Final publication assertions cover all ten adapter fixtures, preserving the
pre-existing source test assertions; EIS pubdate path normalization was corrected
after static inspection of _local_name, without changing adapter evidence/fields.

All **six JS suites PASS**, each exit 0, using existing local tools/HTML:

```powershell
$phase24Node = '.cache/phase24p0-local/.phase24p0-tools/node-v24.21.0-win-x64/node.exe'
$phase24Dashboard = '.cache/phase24p33-completion/dashboard.html'
foreach ($suite in @('company','discovery','discovery_full_ai','phase24r','premium','shortlist_ui')) {
    & $phase24Node "tests/js/$suite.test.cjs" $phase24Dashboard
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
python -m compileall -q app tests/test_analytics_dates.py
git diff --check
```

Compileall and diff-check **PASS**. Authored untracked Python/docs were checked
separately for syntax, trailing whitespace and conflict markers. Actual local UTC
and Europe/Rome ZoneInfo data available; spring/fall DST cases executed, and an
injected unavailable loader also passed. No installation or timezone download.

HEAD **93f02eb38b6570977248af10f4dcb01b4809f8fc**, branch
**phase24-professional-saas-core** unchanged. Earlier uncommitted/untracked work
and existing .tmp-phase24 directories preserved. No network/browser requests,
dotenv/secrets/credential reads, production, real DB migration, Docker, staging,
commit, push or deploy. **PRODUCTION_TOUCHED=False**.

Recommended next checkpoint: 24P.3.7 deterministic authorized selected-history
aggregates using these exact date/fit/identity policies, retaining 24P.3.5 storage
coverage limitations explicitly. P3.7 is a recommendation only, not begun here.

## 24P.3.7 - 2026-10-11 - COMPLETE for supported offline aggregate service

This record supersedes earlier planned/not-begun status ONLY for 24P.3.7.
The tested checkpoint is the pure service and authorized history loader, not an
analytics API, dashboard consumer or browser acceptance.

Independently verified predecessor first: guarded `p37-baseline-p36`, the final
six-file P3.6 selection: **216 passed**, exit **0**, 30.55s. Pasted predecessor
CODEX_EXIT/ENV_UNCHANGED markers were not used as its test-summary evidence.
No serious P3.6 prerequisite defect was found. P3.5 storage/retention limitations
remain explicitly disclosed.

Added `app/analytics/service.py` and `tests/test_analytics_service.py`:

- Complete authorized H iteration, batches 1..20, frozen P3.5 ID/as-of watermark,
  UTC search interval, no 50/100 cap. Every batch and final read reauthorize
  membership/company. Permission/storage errors propagate, never fake empty U.
- Second bounded pass detects body deletion/modification at unchanged event count,
  including already-read snapshots. Concurrent backdated inserts above the fence
  stay excluded. Changed event IDs/partial coverage remain explicit; no durable
  immutability, retention coverage or deleted-byte recovery claim is made.
- Pure timestamp/ID/first-ordinal union, strict source/external identity,
  duplicate/invalid/missing/conflict diagnostics, snapshot hashes/row ordinals,
  version/digest provenance, sample interval and one supplied deadline anchor.
  D/H/R stay distinct; no tender-identity-only joins or lifetime/all-market totals.
- Six KPI slots, source/country/category manifests and overlap/unknown coverage,
  EXACT P3.4 disjoint fit bands/current versus historical fit, distinct publication/
  release/update/search/deadline distributions, P3.6 UTC/date-only windows and
  heatmap identity sets, deterministic eligible top opportunities. Unavailable/
  partial values have reasons and observed numerators; failed searches are not
  successful zero-result observations. No UI/HTTP wiring was added.
- Ten existing metadata groups: known analyzed U versus all U denominators,
  per-group gaps/unknowns, zero price/security presence, separate enrichment
  coverage and metadata/revision conflicts. No absent-analysis scored zero,
  cross-currency total or incomplete-value average.
- Persisted attempted/success/failed source samples, recorded successful zero
  notices, partial/total flags and duration coverage. Missing durations and
  unobserved sources are unavailable; no uptime/SLA/live-health/outage claim.

Algorithms, reasons, exact fixture proofs and downstream requirements:
[P3.7 aggregate contract](docs/PHASE24P37_ANALYTICS.md). Existing SAM.gov/AusTender
offline source fixtures produce supported country/category/date aggregates;
controlled synthetic cases are explicitly labeled, not live published captures.

Verified overlapping test counts (do not add):

- Final focused **241 passed**, exit **0**, 26.19s, seven files, including **60 new
  service tests**. Exact command:

```powershell
python .cache/phase24p3/run_tests.py p37-final tests/test_analytics_service.py tests/test_analytics_dates.py tests/test_analytics_normalization.py tests/test_analytics_fit.py tests/test_company_history_paging.py tests/test_discovery_history_api_behavior.py tests/test_discovery_history_repository.py
```

- Final broad **833 passed + 390 subtests**, exit **0**, 192.32s; **49 files**,
  no skips/deselections. Exact command is the P3.6 `p36-broad` 48-file command
  preserved above, with run name `p37-broad-final` and
  `tests/test_analytics_service.py` added as the first test file. This final broad
  run includes all final service/body-verification changes and race assertions.
- Earlier broad `p37-broad`: **831 passed + 390 subtests**, exit 0, 180.69s,
  before final refinements. Earlier focused `p37-focused`: **239 passed**, exit 0,
  22.07s; `p37-focused-final`: **239 passed**, exit 0, 24.24s. Initial service
  `p37-service-first`/`p37-service-refinement`: **45 passed** each, exit 0.
  No failed regression assertion was changed or weakened.
- **Six JS suites passed**, each exit **0**: company, discovery, discovery_full_ai,
  phase24r, premium, shortlist_ui. Existing portable Node v24.21.0 and
  `.cache/phase24p33-completion/dashboard.html` reused; no installation/browser.
- `python -m compileall -q app/analytics tests/test_analytics_service.py`: PASS.
  `git diff --check`: PASS (existing LF/CRLF notices only). New untracked service,
  test and doc files separately checked for whitespace/conflict markers: PASS.

Guarded Python runs blocked external connects and dotenv opens. One existing
Starlette warning remains. Relevant offline regressions only: not full-repository,
PostgreSQL runtime, live-source, complete UI or browser tests. Exact set/count
assertions cover >100 events, tied latest revisions, event/body deletion,
concurrent insert, corrupt/duplicate-key/nonfinite JSON, missing storage, roles,
revocation/cross-scope/internal population integrity, existing forged cursor cases,
metadata zeros, stale/invalid previews, overlap, naive/no-zone/unknown dates,
spring/fall DST, exact seven-day ends, attempted-success-failure and absent timings.

**P3.7 COMPLETE** is limited to this supported verified offline service checkpoint.
P3.5 remains PARTIAL for retention/immutability/general R and PostgreSQL limitations.
P3.3 remains **PARTIAL** for actual published XML integration; P3.2 consumer
end-to-end verification pending; P2 browser acceptance **PENDING**.
Next recommendation: P3.8 secure API/replay with reauthorization, signed/server-owned
population binding, public-field serialization and snapshot drift rejection.
P4/P5/P6 and production remain OUT OF SCOPE. Pure identity consistency is not UI
acceptance, and current Discover cannot yet replay this H service population.

Pre-existing tracked/untracked work and `.tmp-phase24*` directories preserved.
No source/auth/Saved/PDF/scoring formula/profile change, network, secret/env read,
installation, Docker, migration, staging, reset/checkout/clean, commit/push/deploy
or production operation. **PRODUCTION_TOUCHED=False**.

## Phase 24P.3.8 — secure read-only company analytics API — PARTIAL

This checkpoint supersedes the earlier PLANNED P3.8 roadmap entry; no P4/P5/P6
work is authorized or implemented. Current uncommitted branch and all earlier
tracked/untracked work, snapshots and `.tmp-phase24*` directories are preserved.

### Actual baseline audit

Read the actual registration/session authentication/role/company/history/signing
code, P3.4 fit, P3.6 dates, P3.7 service/tests and the P3.5/P3.7 documentation.
Independent guarded baseline `p38-baseline`: **241 passed**, exit **0**, **21.19s**,
no skips/deselections, seven files from the final P3.7 focused command. The supplied
CODEX_EXIT without a full summary was not treated as proof. No blocking P3.7
defect was found; its pure observed-history service remains **COMPLETE** for the
documented subset, with retention/immutable-storage limitations unchanged.

### Additive implementation

New files: `app/api/analytics_routes.py`, `app/api/analytics_schemas.py`,
`tests/test_analytics_api.py`, `docs/PHASE24P38_ANALYTICS_API.md`.
Only `app/api/main.py` registers the router in the existing API path.
P3.7 gains an optional internal `frozenset` predicate manifest; existing callers
and all existing assertions are preserved.

Exact authenticated read-only endpoints:

* `/api/v1/organizations/{organization_id}/companies/{company_id}/analytics/v1/history/aggregate`
* `/api/v1/organizations/{organization_id}/companies/{company_id}/analytics/v1/history/rows`
* `/api/v1/organizations/{organization_id}/companies/{company_id}/analytics/v1/history/replay`
* `/api/v1/organizations/{organization_id}/companies/{company_id}/analytics/v1/capabilities/D`
* `/api/v1/organizations/{organization_id}/companies/{company_id}/analytics/v1/capabilities/R`
* `/api/v1/organizations/{organization_id}/companies/{company_id}/analytics/v1/capabilities/P`

Population, row and aggregate models carry fixed H identity, server-selected
event IDs, watermark, server UTC AsOf/retrieval AsOf, scope/current digest,
policy/parser/engine/taxonomy versions, historical preview trust, required display
timezone, window, normalized filters, coverage/unknowns/exclusions and capabilities.
All predicates, distributions, top order and row paging share one selected H
population. Source observations/cardinality remain explicitly event-scoped;
their tender drilldowns are distinct from source/country units. Full response
examples, parameters and threat model are in PHASE24P38_ANALYTICS_API.md.

Current session (`touch=False`), owner/admin/member/viewer membership and explicit
company authorization precede history access and token processing, with final
session/membership/company/profile checks before returning. All repository batches
also reauthorize. Forbidden reads are errors, never empty 200 aggregates. Company
IDs are positive bounded 64-bit integers; missing authorized companies are 404.

No cache, replay storage or new secret: existing app HMAC abstraction signs account,
org/company, full normalized query, versions, page/order/window, profile digest,
original fence/count, one-hour expiry and full event-byte SHA256 commitment.
Replay repeats the same fence, excluding later backdated inserts; another full
same-fence load after calculation detects changed/deleted snapshots/metadata.
Changed profile/population is 409, bad/expired/mixed tokens and controls 422,
missing/corrupt storage or budget excess 503, authentication 401, forbidden 403.
No credential/connector error/raw tender body or malformed score is serialized.

D has no verified immutable current snapshot; R aggregation is unsupported and
never reads another account's runs; P lacks immutable company/profile/document
binding. They return explicit typed unavailable capabilities. No fresh Discover,
tender-identity join, AI, rescoring, enqueue, writes, session touch or Saved/PDF
mutation occurs on these reads. Preview bands and unknown/stale digest semantics
remain P3.4; historical fit is not current-profile fit or win probability.

### Limits, status and next gate

500 selected events; 5,000 persisted row occurrences/union rows; 8 MiB per snapshot;
16 MiB selected event bytes; 2 MiB response; 1..100 rows/page; at most 102 bounded
batch calls including independent final verification; cooperative 10-second budget.
Limits fail explicitly instead of truncating 50/100 events or inventing totals.
The 123-event test verifies all exact IDs with equal timestamps and a later
backdated insert. Stored selected searches are sampled H, never lifetime market
coverage. Token commitments do not restore deleted history bytes.

**P3.8 remains PARTIAL:** P3.5 materializes DB strings before application byte checks;
its COUNT/query execution cannot be interrupted by the cooperative timer. Hard DB
wall-time and peak-materialization bounds against oversized storage are not proven.
No live PostgreSQL acceptance or real browser/consumer test was possible within
this offline scope. Do not promote the full cost/time acceptance to COMPLETE.
Recommended P24.3.9: record migration/index decisions from query-plan evidence,
evaluate portable bounded-body/preflight reads and statement cancellation budgets,
then repeat compatibility/security acceptance. No schema change is implied.

P24.2 browser acceptance remains **PENDING**; published TED/CPV P3.3 remains
**PARTIAL**; unpublished eForms SDK samples are not customer data. P3.2/P3.6
limitations remain, and real chart/UI work stays P24.4+. Production untouched.

### Measured validation

Final focused command (eight files):

```powershell
python .cache/phase24p3/run_tests.py p38-acceptance-focused tests/test_analytics_api.py tests/test_analytics_service.py tests/test_analytics_dates.py tests/test_analytics_normalization.py tests/test_analytics_fit.py tests/test_company_history_paging.py tests/test_discovery_history_api_behavior.py tests/test_discovery_history_repository.py
```

Result: **290 passed**, exit **0**, **139.51s**, no skips/deselections. This includes
49 API tests. It follows the deadline equality fix (`>=`), but precedes the final
64-bit path bounds and low-level authorization storage exception mapping.
Those final guards: `p38-storage-final` **2 passed / 47 deselected**, exit 0,
9.64s; `p38-id-final` **9 passed / 40 deselected**, exit 0, 33.60s. The latter selects
`tampering_expiration or denied_before or known_kpis or signing_unavailable`.
Final all-API recheck `p38-final-api`: **49 passed**, exit **0**, **363.81s**, no
skips/deselections; includes final path/storage guards. Final broad
`p38-acceptance-broad`: **882 passed + 390 subtests**, exit **0**, **543.45s**, no
skips/deselections, 50 files. It precedes the last path/storage guards, which are
covered by the all-API recheck. Runtime durations are observations on this host,
not a latency benchmark or concurrency-performance acceptance.

Last narrow budget correction: check elapsed time after each DB batch and after
final authorization, so an over-budget final statement cannot produce 200.
`p38-budget-final`: **3 passed / 47 deselected**, exit **0**, **6.66s**, selecting
`budget_expiration or duplicate_conflicts or known_kpis`. This includes a new
direct bounded-read regression that expires INSIDE the last database call, plus
exact row/KPI/replay and limit integration tests. The API test file now contains
50 cases; 49 passed in the full recheck, the additional case passed in this narrow
recheck. Full focused/broad runs precede this last narrow guard; counts overlap.
The SQL operation still cannot be interrupted; the PARTIAL blocker is unchanged.

Broad selection is exactly the preserved 48-file `p36-broad` command above, adding
`tests/test_analytics_service.py` and `tests/test_analytics_api.py` (50 files).
Run name `p38-acceptance-broad`. Earlier broad `p38-final-broad`: **880 passed +
390 subtests**, exit 0, 318.57s; predates final deadline equality/path/storage guards
and two additional tests. Counts overlap and are not additive.

Six JS suites: **6/6 passed**, each exit 0 — company, discovery, discovery_full_ai,
phase24r, premium, shortlist_ui. Existing portable Node v24.21.0 and
`.cache/phase24p33-completion/dashboard.html` reused, no installations/browser.
`python -m compileall -q app tests`: PASS. `git diff --check`: PASS; new untracked
API/service/test/doc files separately checked for whitespace/conflict markers: PASS.
One existing Starlette deprecation warning; no secret-dependent tests, live API,
production, Docker, migration, staging, commit, push or deploy.

Initial new API schema cardinality mismatch was fixed; a new duplicate fixture
was corrected to repeat identical bytes instead of independently timestamped
objects. A zero-budget test exposed Windows timer equality and the boundary was
fixed; failed runs are not acceptance evidence. Existing tests were not weakened.
**PRODUCTION_TOUCHED=False**.

## 24P.3.9 - PARTIAL - Compatibility, migration-readiness and evidence gates

The P3.9 roadmap status is superseded by this verified subset only. Exact
compatibility/version/KPI matrix, migration and rollback decisions, resource and
race limits, commands and unsupported acceptance are in
[PHASE24P39_COMPATIBILITY.md](docs/PHASE24P39_COMPATIBILITY.md).

Independent P3.8 baseline: **118 passed**, exit 0, 119.20s, no skips/deselections;
all 50 analytics API cases plus service and company-history paging. P3.8 remains
**PARTIAL**; previous CODEX_EXIT without summary was not treated as proof.

Delivered narrowly scoped opt-in SQLite analytics preflight (500 events, 16 MiB
selected JSON/source bytes, 8 MiB snapshot before Python body materialization),
query-only connection and SQL progress cancellation. API JSON complexity is
bounded; shared paging rejects deep unsigned token/UTC overflow as 422.
Legacy repository paging, public endpoints, source adapters, score thresholds,
Saved, PDFs and UI remain unchanged by P3.9. Non-SQLite bounded analytics fails
closed with 503 until actual backend proof; legacy PostgreSQL calls are unchanged.

New 23-case release suite covers disposable fresh and unledgered-v1/ledger-11
upgrades, exact old H/S/P/R revision preservation and D/S/P decode, new sidecars,
unknown version/checksum refusal, mixed policies, byte/complexity limits, actual
SQLite VM cancellation/read-only operation, scope/errors/token invalidation,
credential allowlist, existing SAM/AusTender parser-to-API/replay and runner guards.
No existing assertion was weakened. Initial new-test failures and corrections
are recorded in the compatibility document rather than counted as acceptance.

**No new migration required or added.** schema_meta=1, existing ledger 1..13
and frozen schema/checksums retained. SQLite EXPLAIN uses the existing scoped
history index without temporary sort; no evidenced new index needed. Fixture
bootstrap upgrades ran only in new isolated .cache/phase24p3 DBs. No real user/
production DB access, backfill or migration; no migration execution proposed.

Final measured evidence (overlapping counts):

- `p39-final-all-gates`: **314 passed**, exit 0, 178.57s, 9 files, no skips/deselections.
- `p39-broad-final`: **1465 passed, 2 skipped, 390 subtests passed**, exit 0,
  377.30s, 57 files, no deselections. Skips are the two existing raw-deflate
  checksum cases; one existing Starlette warning. This includes final app changes.
- `p39-release-guard-final`: **23 passed**, exit 0, 32.46s, no skips/deselections,
  after final guard-only Windows dotenv aliases/forward-reverse DNS extension.
- All six local JS suites passed, each exit 0, existing Node/current dashboard.
- Compileall, git diff --check and separate 44-file untracked AST/JSON/hash/
  whitespace/conflict review passed; original SDK XML whitespace retained.

Offline runner blocks external connect/connect_ex/UDP/DNS and dotenv opens;
guard proof uses synthetic audit events, no secret reads. PostgreSQL foundation/
harness tests are mocks/SQL/SQLite, not actual server coverage. No postgres/psql
command was found; no authorized disposable PostgreSQL runtime was used.

**P3.9 PARTIAL; P3.8 PARTIAL; overall P3 not COMPLETE.** Whole-request hard
time/peak-memory/concurrency proof, P3.5 retention/manifest/UI limits, D/R/P
analytics positives and published TED context/industry evidence remain unresolved.
**P24.2 real-browser acceptance PENDING; published P3.3 PARTIAL.**
Recommendation: do not open full P24.4 charts rollout gate. P24.4/P24.5/P24.6
remain NOT STARTED. Prior uncommitted/untracked work and .tmp-phase24 folders
preserved; no network/secrets/install/Docker/staging/commit/push/deploy/production.

PRODUCTION_TOUCHED=False


## Phase 24P.4 prerequisite review (2026-10-11)

**P24.4 BLOCKED; charts not implemented.** This is the current checkpoint
assessment, superseding earlier P4 PLANNED/NOT STARTED status only. The exact P4
roadmap depends on P2/P3, and the final P39 closure explicitly withholds full P4
rollout. Code review confirms incomplete hard whole-request time/memory and
backend-runtime acceptance: SQLite limits SQL/body reads, while non-SQLite bounded
analytics fails closed with 503. These are backend prerequisite work, not a narrow
chart fix. The user's instruction permits marking P4 BLOCKED in this situation.
No application or existing test edits were made; existing uncommitted work remains.

See docs/PHASE24P4_CHARTS.md for reviewed contracts, future field mapping,
unsupported charts, existing security guarantees and unimplemented consumer gates.
All six premium KPI cards/chart panels remain unavailable; no live-data, chart,
replay or browser acceptance is claimed. P3.8/P3.9 remain PARTIAL, published P3.3
XML integration PARTIAL, P2/P4 browser PENDING, P5/P6 unstarted. No production,
external network, secrets, installation, Docker, migration, source crawl,
staging/commit/push or preexisting .tmp-phase24 edits.

Measured verification (existing guarded runner, current code, offline fixtures):

- Focused baseline `p4-baseline-20261011`: **314 passed, 0 skipped, 0 deselected**,
  exit **0**, **249.52s**, nine explicit files, including all 23 P39 release cases.
- Broad `p4-broad-20261011`: **1465 passed, 2 skipped, 390 subtests passed,
  0 deselected**, exit **0**, **492.82s**. Exact 57-file P39 final broad selection;
  only the run directory changed. Skips: test_source_http.py:805/:1000 (raw
  deflate has no checksum). Focused cases overlap this run; do not sum totals.
- One existing Starlette TestClient/httpx deprecation warning in each Python run.
- All six existing local JS suites passed individually, exit 0: company,
  discovery, discovery_full_ai, phase24r, premium, shortlist_ui. Existing portable
  Node v24.21.0 and current-render p4-dashboard.html; no browser launched.
- compileall app/tests/scripts and git diff --check passed. Separate untracked
  inspection: **45 files**, AST/JSON/merge-marker/whitespace/manifest checks;
  one original SDK XML comment whitespace retained for byte fidelity. No other
  untracked errors. No new chart tests: no chart implementation was added.
- These are supported-subset results, not a full-repository/browser/live-source/
  PostgreSQL server/production acceptance. ENV_UNCHANGED was not independently
  measured. No narrow repair or assertion weakening was required.

**P3.9 independently verified PARTIAL; P24.4 BLOCKED.** Resolve the documented
P38/P39 backend resource/runtime rollout gate, then implement and accept the H
chart consumer. Recommend P24.5 only after accepted P24.4; do not start it now.
PRODUCTION_TOUCHED=False


## P24P.3.9D local real-H fixture worker checkpoint (2026-10-11)

**P3.9 PARTIAL; P4 full rollout BLOCKED; strictly offline development.**
New fixed-fixture adapter/spike really executed existing aggregate_history() in
Windows child workers under Job Objects; all six KPI/identities/denominators/
unknown-versus-zero/profile/timezone/as_of/filter and legacy/foreign/future policy
parity verified. P39B remains unchanged synthetic-only and unwired. No API/UI/
admission/DB/migration wiring. See appended P39D evidence in
[PHASE24P39_RUNTIME_GATE.md](docs/PHASE24P39_RUNTIME_GATE.md).
Baseline 85 PASS (21.07s), new final 43 PASS (7.74s); relevant ten-file regression 372 PASS (203.81s), exit 0, 0 SKIP.
All exit 0, no skips/deselections; overlapping counts are not additive.
Six JS suites, compileall new modules/tests and diff-check PASS; no browser.
128 MiB committed-memory cap supports this tiny fixture: ~34 MiB measured peak
commit, ~44 MiB peak working set. NOT CPU/RSS or whole-request isolation.
Popen-before-job-assignment startup gap persists; ordinary user token/audit hooks
are not an OS sandbox. Parent final authorization is required for any future API.
399 prior files/doc byte prefixes preserved; .tmp-phase24* untouched. Hash setup
inadvertently read two tracked dotenv EXAMPLE templates (no contents printed,
no actual .env); subsequent preservation checks exclude them and run guarded.
No production/network/install/live DB/commit. All changes remain uncommitted.
ONE next checkpoint: default-off, loopback-only fixture LOCAL H charts preview
using this real-H output, optionally disposable query-only SQLite; no PostgreSQL
requirement for that local preview and no production rollout authorization.
PRODUCTION_TOUCHED=False.


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
commands, exact path and limitations: [local preview](docs/PHASE24P39_LOCAL_PREVIEW.md).

Existing tracked/untracked edits retained; .tmp-phase24* not opened/cleaned.
No DB, production, network, installation, commit/push/deploy or migration.
PRODUCTION_TOUCHED=False.


## P24P.3.9F — local fixture visual polish (2026-10-11)

Scoped edits only: scripts/p39e_preview/page.html, style.css, view.js, matching
viewer tests and these local progress documents. Production dashboard, premium
assets, core analytics, fixture commitment and worker logic were not edited.
Local fixture preview improved; P3.9 PARTIAL / full production P4 still BLOCKED /
no P5. Original P39E evidence above is preserved.

Russian user labels, restrained navy header with light evidence panels, balanced
card heights, neutral priority accents for High Fit and closing deadlines, chart
legend, exact denominators, explicit historical preliminary relevance (not win
probability), observed successful sources (not live health), typed calendar/date
versus instant deadlines, and clearer evidence table. Exact identities remain
in drilldowns/table; raw metric evidence/reasons are retained in expandable
technical provenance. Unknown/null remains distinct from zero. No client scoring,
new figures, network resources or production routes. Native buttons retain click,
focus and Enter/Space behavior; keyboard activation itself still needs a browser.
Fit values now also reject unsafe numeric contract values before rendering.

Baseline guarded Python: 123 passed, exit 0, 20.34s (P39E + offline spike + service).
Baseline viewer JS on original generated HTML: exit 0. Initial all-JS command
omitted mandatory HTML arguments for company/phase24r/viewer and returned exit 1
for those invocations; corrected calls all passed, not product failures.
Final local Python: 21 passed, exit 0, 7.28s, including Russian presentation and
rendered CSP hash checks. Final JS viewer and all six existing suites: each exit 0
(company, discovery, discovery_full_ai, phase24r, premium, shortlist_ui).
Company/phase24r use existing .cache/phase24p3/p39d-dashboard.html; viewer uses
actual rebuilt .cache/phase24p3/p39e-preview/index.html. Tests verify seven cases,
normal [4,2,2,1,1,1], unknown/zero, filtered and typed deadlines, drilldown/stale
clearing/retry/error recovery, numeric failures, accessible labels and responsive
layout rules. DOM harness is not real browser acceptance. compileall exit 0;
git diff --check exit 0 with existing CRLF warnings only.

Two final explicit --build-fixture builds identical: 46453 bytes, SHA256
805345b466eab63b50802cd77b727316cd343ca26e6e0f0af71b4a3f55878d29.
Default-off remains DISABLED and preserves the output hash. CSP script/style
hashes match rendered content; no external resources/connections are added.

Browser acceptance: user-supplied prior desktop descriptions establish only the
original P39E desktop render. No Edge/Chrome executable found at standard Program
Files Edge/Chrome or per-user Chrome paths. No browser launched, installed,
networked or attached; no additional screenshots captured. Updated desktop,
360px visual, real keyboard, file-origin CSP and accessibility acceptance remain
PENDING. Next single practical step: open the rebuilt file and provide a 360px
screenshot (ideally after opening a card with Enter/Space).

```powershell
Invoke-Item $HOME\Documents\Codex	ender-ai-phase19\.cache\phase24p3\p39e-preview\index.html
```

All prior tracked/untracked work and .tmp-phase24* preserved. No stage/commit/
push/deploy, server, installs, customer database or secret reads.

Final bounded regression: 198 passed, exit 0, 180.35s, one existing
Starlette/httpx deprecation warning. Command:
`python .cache/phase24p3/run_tests.py p39f-final tests/test_p39e_local_preview.py tests/test_analytics_offline_spike.py tests/test_analytics_process_isolation.py tests/test_analytics_api.py tests/test_analytics_service.py`.
This run started with the original 20 local tests; the final 21-test local suite
ran separately after the presentation/CSP test addition. Counts overlap and are
not additive. No failing test assertions were changed or weakened.

### P24P.3.9G — dark local command center, 2026-10-11
Полная перестройка standalone fixture viewer: navy shell/sidebar, компактные KPI,
SVG donut known historical fit + separate unknown, typed deadline tracks,
поиск/fit/deadline фильтры/сортировка/reset и точные identity drilldowns,
evidence inspector и technical disclosure. Клиент не пересчитывает KPI/scoring.
Baseline guarded local Python 21 pass и прежний viewer JS pass. Финальные
семь JS suites pass; compileall и diff --check exit 0. Две сборки identical,
54894 bytes, SHA256 bca0a213987a1122def9f6d75fccbbee2d008cd1160b6aecb54b6755032e0d07.
Подробности и промежуточные ошибки: docs/PHASE24P39_LOCAL_PREVIEW.md.
Chrome/Edge по стандартным путям нет; реальные desktop/360px screenshots и
keyboard/file-origin CSP acceptance PENDING. Без server/network/production.
P3.9 PARTIAL; P4 public rollout BLOCKED; P5 НЕ ВКЛЮЧЁН.
Окончательная guarded Python регрессия P39G: 199 passed, exit 0, 188.69s,
пять явных local/spike/isolation/API/service test files; одно прежнее
Starlette/httpx warning. Отдельный local: 21 passed, exit 0 (counts overlap).
Промежуточные 197 pass / 2 local failures (BOM, старый label assertion)
исправлены и честно записаны в local preview документе.

### P24P.3.9H / A — полная локальная основа EN/RU, 2026-10-11

Единый словарь 132 явных en/ru ключей, английская страница до JS, заметный EN/RU
переключатель, локализация всего статического/динамического интерфейса и ARIA,
Intl-представление без пересчёта данных, сохранение языка с обработкой отказа
localStorage. Фильтры/сценарий сохраняются, старый drilldown очищается.
Normal KPI [4,2,2,1,1,1], все семь trusted scenarios без изменения worker/fixtures.
Финальный Node i18n и прежний viewer suite PASS / exit 0; guarded Python viewer:
23 passed / exit 0 / 6.79s. Сборка только --build-fixture: 70 921 bytes,
SHA256 32d181b9502db761c4b1b385bda0a7af37b59329bde7cf841951420fc0ebdf49.
Без флага DISABLED, файл не меняется. Реальный headless browser test предпринят,
но браузер завершился при запуске в ограниченной среде (exit 1); screenshots и
браузерная/клавиатурная приёмка PENDING. Все промежуточные ошибки и корректный
guarded test setup описаны в docs/PHASE24P39H_LOCAL_I18N.md.
Только offline preview; production не менялся. P3.9 PARTIAL; PUBLIC P4 BLOCKED;
P5 не включён. Следующие этапы и настоящая desktop/360px приёмка ещё впереди.

## Этап B/4 — 2026-10-12: визуальные инструменты реализованы, приёмка заблокирована

P3.9 PARTIAL; PUBLIC P4 BLOCKED; P5 не включён. Только автономная вымышленная выборка.

Изменения:
- scripts/p39e_preview/page.html: общий адаптивный контейнер explorer/inspector.
- scripts/p39e_preview/style.css: тёмная композиция navy, тонкие разделители, глубина панелей,
  шесть акцентированных KPI с пояснениями, двухколоночное рабочее место на desktop,
  отдельные стили instant/date_only, узлы SVG, hover/focus, mobile/tablet breakpoints,
  отключение переходов при prefers-reduced-motion. Светлый режим не добавлен.
- scripts/p39e_preview/view.js: десять новых ключей общего EN/RU словаря; контекст каждого KPI;
  внешний контур known / U отдельно от внутреннего распределения known;
  декоративные узлы подтверждённых дат без выдуманной временной шкалы;
  переведённое объяснение расстояний и клавиатурные подсказки в title.
  Математика model/arcs, идентификаторы, фильтры, сценарии и сохранение языка не изменены.
- tests/js/p39h_visual.test.cjs: новый тест пути к штатному HTML, CSP-хешей реальных байтов,
  dark/responsive/motion, EN/RU, знаменателей, идентификаторов и обязательного наличия
  обеих групп сроков в normal; включает i18n suite.
- tests/js/p39h_i18n.test.cjs: обход SVG на конечные неотрицательные координаты,
  безопасный фиксированный path, переведённые новые подписи/title и native buttons.
- tests/test_p39e_local_preview.py: дополнительный контракт композиции и графических инструментов.
- Builder и существующий tests/js/p39e_preview.test.cjs не изменялись; app/ и fixtures не редактировались.

Фактические запуски и ограничения:
1. Найденный Python 3.12: штатный --build-fixture exit 1 (сначала отсутствует pydantic).
   Повтор с существующими каталогами кэша через PYTHONPATH: exit 1, child_exit.
   Изолированный worker получает один каталог зависимости и не видит раздельные зависимости кэша.
   Установок, сети и изменений worker не было.
2. Для диагностики render(calculate(...)) выполнялся исключительно в памяти.
   Это НЕ успешная worker-сборка и НЕ восстановленный index.html.
   В этом runtime отсутствует база часовых поясов; normal deadline buckets пусты.
3. Настоящий Node v24.21.0: i18n suite прошёл на диагностическом HTML в памяти.
   Первоначальная visual-проверка прошла, но после добавления обязательного покрытия обоих
   типов сроков финальный visual suite правильно падает из-за пустых buckets.
   Старый p39e suite падает на ожидании deadline sort ted/high: без дат первым идёт ted/calendar.
   Ожидание сохранено, тест не ослаблялся.
4. Шесть функций Python artifact/security/layout tests выполнены напрямую из AST тестового
   файла на диагностическом calculate-результате: PASS (HTML/security, CSP/labels/layout,
   EN fallback, i18n contract, stage B contract, отсутствие server/app mutation).
   Это НЕ полный pytest suite: pytest отсутствует в доступном runtime.
5. Два диагностических render побайтово одинаковы: 77059 байт,
   SHA256 37d5959b42cd7820cf013ae50af88992463d58ce4fa2d2744c6c5f6ab4683e68.
   Две последовательные штатные сборки НЕ подтверждены.
6. Без флага main([]): DISABLED, exit 0.
7. Браузер не запускался, screenshots и визуальная приёмка 360/tablet/desktop отсутствуют.
   Адаптивность проверена только контрактами CSS/DOM.
8. Штатный builder удаляет предыдущий успешный index.html до попытки сборки.
   После неуспешных запусков финальный .cache/phase24p3/p39e-preview/index.html отсутствует.
   Нельзя подменять его диагностическим HTML; нужен успешный --build-fixture в полном runtime.

Для следующего этапа нужен уже установленный полноценный runtime с pydantic и его зависимостями
в общем доверенном каталоге и базой IANA timezone, плюс pytest. Затем штатная сборка дважды,
три Node suites по фактическому index.html, полный Python viewer suite и реальная offline
браузерная приёмка. Этап B не объявлен принятым.

## 2026-10-12 — Stage C/4: local interaction instruments
P3.9 PARTIAL; PUBLIC P4 BLOCKED; P5 DISABLED.

Implemented only preview assets:
- view.js: row inspection preserves search, filters, order and current group instead of reducing the list to one row. Record selection uses aria-pressed and a distinct visual state. Group buttons expose aria-controls and synchronized aria-pressed. Clear selected group restores the population while retaining user filters. Reset clears group/record selection. Scenario and language rendering clear stale selection; scenario resets all inputs. Visible counts now explicitly label the frozen indicator population.
- page.html: genuine EN/RU Clear selected group and Back to records controls. The former is disabled when no group exists; the latter scrolls to explorer and returns keyboard focus to its first result.
- style.css: selected evidence states, disabled-state appearance, narrow toolbar bounds; existing dark hierarchy, 360px rules and reduced-motion retained.
- tests/js/p39h_interactions.test.cjs: accepts generated HTML, verifies EN/RU × seven scenarios, exact group identities/counts, row/search preservation, group clearing, focus return, anchors, errors, restoration, fixture immutability and native button semantics.
- tests/js/p39e_preview.test.cjs: DOM harness registers the three new nodes; existing assertions unchanged. No worker, builder, app or fixture bytes edited.

Actual verification:
1. Standard --build-fixture attempted twice: BUILD FAILED, no successful index.html. First runtime lacks installed dependencies; cached dependencies via PYTHONPATH still do not satisfy isolated child worker. No dependency installation or worker bypass.
2. Four final Node suites PASS on diagnostic HTML rendered in memory from trusted calculate for all seven cases using existing cached dependencies: interactions, i18n, visual, existing viewer. Base64 transport preserved UTF-8 and CSP bytes. Diagnostic HTML was never saved as index.html and is NOT worker/build acceptance. Normal KPI [4,2,2,1,1,1]; both typed deadline tracks verified by unchanged visual suite.
3. Seven existing Python contract functions executed directly from AST under offline audit guard: semantics, safe HTML, no app mutation/server, CSP/layout, EN fallback, i18n contract, Stage B layout PASS. This is NOT the full pytest suite or worker equivalence.
4. Full viewer pytest attempted: No module named pytest, exit 1. Default launcher remains DISABLED, exit 0.
5. Browser/screenshot acceptance NOT performed. Real Enter/Space activation and 360px rendered layout remain unverified; native buttons/focus/CSS contracts are covered only by DOM tests.
6. Intermediate test failures: shell interpolation introduced invalid JS; corrected before final PASS. Diagnostic stdout text transport changed UTF-8/newlines; corrected via base64 without weakening assertions.

CSV deliberately omitted: no validated file:// download/browser runtime. No P5 widgets, live source monitor, invented analytics or network calls. Remaining acceptance requires a complete existing trusted Python runtime (dependencies together for isolated worker, pytest, timezone database), standard --build-fixture, all suites on its real HTML and offline browser review. Stage C is implemented but NOT accepted as a final built/browser artifact.

## 2026-10-12 — PHASE24P.3.9H D/4: независимый локальный QA, приёмка заблокирована

OFFLINE TEST FIXTURE; P3.9 PARTIAL; PUBLIC P4 BLOCKED; FULL P4/P5 production NOT implemented.
Только исправления QA: сохранение клавиатурного фокуса строки; удаление неверного пояснения источников/стран из её инспектора; очистка контролов при частичной ошибке; перевод состояния подготовки EN/RU. Усилены контроль всех латинских слов в RU и обязательное точное соответствие кнопок модельным группам; добавлен preview-only offline source contract. Тёмный дизайн и trusted worker/данные не менялись.
Измерено в D: шесть legacy Node suites PASS (exit 0), source contract PASS (exit 0), compileall и git diff --check exit 0. Четыре штатные попытки сборки exit 1; без флага DISABLED exit 0. Четыре обязательных набора на итоговом HTML: каждый exit 1 / ENOENT. Guarded Python для пяти заданных файлов exit 1: нет pytest, 0 собрано. Финальные диагностические i18n/interactions в памяти PASS; viewer/visual FAIL из-за отсутствующих timezone buckets, ожидания сохранены. Диагностические normal KPI [4,2,2,1,1,1], данные не мутируют. Диагностический HTML не записан как index.html.
Приёмка итогового HTML/CSP/двух одинаковых worker-сборок заблокирована неполным установленным Python runtime. REAL BROWSER/360px/MOBILE/KEYBOARD VISUAL ACCEPTANCE PENDING: финального файла нет, браузер и скриншоты в D отсутствуют. Без stage/add/commit/push/deploy, установок и сети. Подробная русская передача и результаты: docs/PHASE24P39H_LOCAL_I18N.md, D/4. Заморозка контракта НЕ принята.

## 2026-10-12 — P4A/4: локальные проверяемые проекции
Реализованы analyticsEvidence в view.js и tests/js/p39j_evidence.test.cjs (путь к штатному generated HTML обязателен). Event activity по UTC, источники по выбранному U, typed worker deadlines, known/unknown fit, покрытие и provenance. Country/CPV identity mappings отсутствуют: явно unavailable, без поддельных нулей. Существующий DOM H и builder сохранены.
Диагностика текущего source в доступном Node REPL на семи случаях существующего HTML: PASS для проекций, неизменности, словаря и небезопасных чисел. Команды Node/Python отсутствуют в PATH; обязательный новый generated-HTML suite, rebuild, Python, protected hash gates и browser/360px остаются launcher pending. Никакой успешный artifact не генерировался обходным способом.
Подробности: docs/PHASE24P4_P5_LOCAL_ANALYTICS.md. OFFLINE LOCAL DEMO; P3.9 PARTIAL; production P4 BLOCKED; production P5 не реализован.

## 2026-10-12 — P4B/4: локальные dark charts, приёмка host pending
Реализованы EN/RU панели источников с exact U drilldown и SVG scale, календарные ячейки
с отдельными instant/date_only, явные unavailable состояния тренда/географии/CPV.
Сохранены шесть KPI, fit donut, фильтры, сценарии и инспектор. Только preview assets;
builder/app/fixtures не менялись. Добавлен tests/js/p39j_charts.test.cjs (generated HTML
обязателен); preservation harness p39e зарегистрировал новый DOM node.
Source DOM диагностика 7 × 2 и H i18n/interactions PASS; offline source contract и
JS syntax PASS. Новый generated suite FAIL на stale bundle; штатная host-пересборка,
полные Node/Python/hash gates и реальная desktop/360px EN/RU визуальная приёмка pending.
Node/Python CLI отсутствуют в PATH; использован имеющийся Node REPL. Артефакт не подменялся,
браузер не инспектировался. Полная передача: docs/PHASE24P4_P5_LOCAL_ANALYTICS.md.
OFFLINE LOCAL DEMO; P3.9 PARTIAL; production P4 BLOCKED; full production P5 не реализован.

## 2026-10-12 — P5A/4: локальный прототип виджетов
Только OFFLINE pinned synthetic demo; P3.9 PARTIAL; production P4 BLOCKED;
full production P5 НЕ реализован. Exact U records sorted by historical band/identity,
coverage known/unknown / U, stored dated search events, source observations, рабочие
filter chips/reset и identity detail panel с focus return. Country/CPV/scores/финансы
явно unavailable, KPI [4,2,2,1,1,1] неизменны. +17 EN/RU ключей, всего 175.
Новый tests/js/p39j_widgets.test.cjs требует generated HTML и проверяет реальные DOM
handlers 7 × 2, identities/counts, язык/фильтры, isolation и keyboard structure/focus.
Source DOM diagnostics P5A/H i18n/interactions PASS; syntax PASS через Node REPL.
Generated suite на прежнем HTML FAIL: stale bundle. CLI Node/Python нет в PATH.
Builder не запускался; artifact не подменён. Host rebuild/Node/Python/hash gates и
реальная offline browser desktop/360px/Enter/Space приёмка pending.
Подробности и честные ограничения: docs/PHASE24P4_P5_LOCAL_ANALYTICS.md, P5A/4.
