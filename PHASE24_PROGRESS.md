# Phase 24 Professional SaaS Core

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

No implementation checkpoint is currently incomplete.

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

All earlier completed milestones, reported test results and the completed Phase 24S.2B.4 security checkpoint remain intact. Their tests and security audit have not been rerun here. Phase 24P.0 filter ownership is fully completed and runtime-verified as recorded below. Dashboard milestones 24P.1-24P.6 remain PLANNED; no dashboard visual acceptance is claimed.

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

#### 24P.1 - PLANNED - Audit real analytics data and tenant scoping

- Goal: inventory existing persisted history versus latest-session discovery, APIs, timestamps, identifiers, preliminary fit/full AI scores, source status and role/tenant boundaries. Produce a supported-metric mapping before implementation, covering all six KPIs, Tender Activity, Company Fit, Global Geography, industry/category/source breakdowns, deadline calendar, Source Health, Data Completeness, Top Opportunities columns, contextual summaries and Discover drilldown predicates.
- Affected files (read-only audit targets; any future edits limited to evidenced needs): `app/api/organization_workflow_routes.py`, `app/api/organization_data_routes.py`, `app/api/scoring_run_routes.py`, `app/organizations/models.py`, `app/organizations/repository.py`, `app/database/repository.py`, `app/scoring/models.py`, `app/api/static/shell.js`, `app/api/static/discovery.js`, `app/api/static/history.js`, `app/api/static/saved.js`; mapping recorded in `PHASE24_PROGRESS.md`.
- Dependencies: 24P.0; existing API/model contracts and authorized organization/company context.
- Acceptance criteria: each proposed metric maps to actual fields, API, persistence/session lifetime, timestamp semantics, deduplication, company applicability and permissions; unsupported metrics explicitly unavailable. Record exact available tender metadata, completeness requirements, fit thresholds/bands, chart denominators and supported Discover filter/navigation contracts, including whether a drilldown can reproduce the aggregate population. Audit determines whether company-scoped history/fit and historical source reports exist rather than assuming them.
- Tests: existing discovery history API/repository, organization data/workflow and scoring contract tests; targeted read-only fixtures for no history, missing dates, unauthorized/cross-tenant access and company-specific score eligibility. Record gaps without inventing services.

#### 24P.2 - PLANNED - Responsive premium shell and six KPI cards

- Goal: implement the approved rich navy command-center shell, asymmetric widget grid and the Discovered/Matched/High Fit/Active Sources/Countries/Closing Soon cards with truthful scope/origin labels and all loading/error/unavailable states.
- Affected files (future implementation): `app/api/saas_shell.py`, `app/api/static/premium.css`, `app/api/static/premium.js`, `app/api/static/shell.js` only where context integration requires it; `tests/test_premium_ui.py`, `tests/test_saas_core.py`.
- Dependencies: 24P.1 supported-metric mapping; existing auth/navigation/context; 24P.3 is required before cards can claim live aggregate results. This milestone may build unavailable-state presentation first.
- Acceptance criteria: compact premium sidebar, organization/company/date topbar, layered deep navy surfaces, indigo/blue/violet accents, elegant typography, varied widget sizes and six responsive cards match the approved first-screenshot direction; the rejected simple sketch is not an acceptance baseline; no fabricated sample figures in the authenticated product; desktop/tablet/mobile reflow, meaningful labels, visible focus and accessible navigation; existing routes, onboarding and controls work.
- Tests: shell/markup regressions, keyboard and focus checks, loading/no-company/unavailable/error cases; real-browser layout checks at representative desktop/tablet/mobile widths remain required, with results recorded only when actually run.

#### 24P.3 - PLANNED - Secure true-data aggregation engine

- Goal: aggregate only metrics supported by the 24P.1 audited models, using declared populations and consistent filters. Reuse existing APIs; add an authenticated aggregate contract only if necessary and supported by existing data.
- Affected files (future implementation, conditional on audit): `app/api/organization_data_routes.py`, `app/api/organization_workflow_routes.py`, `app/api/schemas.py`, `app/organizations/repository.py`, `app/database/repository.py`, `app/api/static/premium.js`; `tests/test_organization_data.py`, `tests/test_organization_workflows.py`, discovery history API/repository tests.
- Dependencies: 24P.1 data/authorization contract and 24P.2 display contract; no missing-service implementation or synthetic historical storage.
- Acceptance criteria: authorized tenant/company scoping enforced before aggregation; viewer read access follows existing rights; deterministic deduplication and explicit null/unknown treatment; preliminary fit never substituted for full AI scoring; supported empty queries may return zero, unavailable inputs cannot. No invented counts/timelines, cross-tenant cache leakage or analytics read mutations; workspace/request epoch invalidates stale responses.
- Tests: known-fixture aggregate correctness, duplicates/nulls/date boundaries/timezones, partial data, empty versus unavailable, cross-tenant and company isolation, viewer rights, unauthorized requests and stale-context races; regression of existing API responses and discovery repeatability.

#### 24P.4 - PLANNED - Interactive analytics charts

- Goal: implement the large Tender Activity grouped bar/area chart, multi-ring Company Fit distribution, Global Geography country/count/horizontal-bar panel, distinct industry/category/source breakdowns and deadline calendar heatmap with interactive shared filters, authorized Discover drilldowns, honest date-range semantics and no-data states.
- Affected files (future implementation): `app/api/saas_shell.py`, `app/api/static/premium.js`, `app/api/static/premium.css`; existing organization data route/schema only if the audited aggregate contract requires it; `tests/test_premium_ui.py` and focused dashboard JavaScript tests added during implementation.
- Dependencies: 24P.2 and 24P.3; timestamp and fit contracts from 24P.1.
- Acceptance criteria: chart/table/card populations reconcile; hover/focus details and legends declare counts, units, denominators and preliminary/full scoring distinctions; filters are keyboard usable and reset predictably; selected date field/window/timezone and unknown-date policy are visible. No history means no historical trend; unsupported classifications, unknown geography, missing deadlines and failed sources show honest explanatory states. Charts never create observations from absent data. Tender Activity buckets use an audited real timestamp and declared grouping; enable area presentation only when supported temporal observations exist, with gaps preserved and no invented interpolation. Geography shows readable country names and real counts; the deadline calendar uses real deadline dates and per-day counts, with missing deadlines separate. Each chart provides readable table/list alternatives and keyboard-operable drilldowns that preserve supported context and predicates or explain why unavailable.
- Tests: chart/table reconciliation against real-schema fixtures, date/range boundaries, unknown categories/countries/deadlines, no history, filter combinations, company switches and stale requests; keyboard/screen-reader alternatives, contrast/reduced motion and responsive browser inspection.

#### 24P.5 - PLANNED - Opportunity, deadline and source-health widgets

- Goal: implement the professional sortable Top Opportunities table, upcoming-deadline, Source Health and Data Completeness widgets, plus compact contextual summaries and actionable business widgets from supported authorized data, with actions connected to existing tender detail, authorized Discover results, Saved and PDF assistant workflows.
- Affected files (future implementation): `app/api/saas_shell.py`, `app/api/static/premium.js`, `app/api/static/premium.css`; integration review of `app/api/static/discovery.js`, `app/api/static/saved.js`, `app/api/saved_ui.py`, `app/api/dashboard.py`; `tests/test_saved_ui_contract.py`, `tests/js/discovery.test.cjs`, `tests/test_organization_pdf_rag.py`, `tests/test_premium_ui.py`.
- Dependencies: 24P.3 data contract and 24P.4 filters; existing role-aware actions and PDF/Saved services.
- Acceptance criteria: recency uses a declared real timestamp; upcoming deadlines use valid dates and stated timezone/window; source health distinguishes success/partial/failure/unknown and latest-search scope from any available historical scope. Actions open the correct scoped record/workspace, preserve viewer restrictions and safe links, and honestly disable unavailable capabilities. Top Opportunities uses only available real tender metadata: title/identifier, source, buyer, country, industry/category, publication date, deadline, value/currency, preliminary fit and completeness where audited fields exist. Unavailable cells remain explicit; ranking uses a declared supported criterion, never an invented AI score. Sorting is deterministic, keyboard accessible, announces direction and handles unknown values consistently; filters, counts and table rows reconcile to the declared population. Data Completeness shows audited present/required metadata counts, unknown states and gaps without implying document acquisition or full analysis readiness. Contextual summaries reference real counts and dates; actions respect role permissions and unavailable capabilities. No fabricated alerts, save counts, revenue, savings or automatic document acquisition.
- Tests: table sorting/ties/unknown cells and supported ranking, table/filter/count reconciliation, completeness numerators/denominators and missing fields, summary accuracy, ordering/date boundaries, missing timestamps/deadlines, partial/total source failure, authorized Discover drilldowns and working navigation/actions, viewer mutation denial, scoped Saved/PDF regressions and workspace changes during requests.

#### 24P.6 - PLANNED - End-to-end acceptance and real-browser validation

- Goal: complete security, regression, accessibility, performance and real-browser desktop/tablet/mobile acceptance before claiming premium visual readiness.
- Affected files (future fixes only when findings justify them): Phase 24P UI/API files listed above and relevant `tests/test_web_auth.py`, `tests/test_premium_ui.py`, `tests/test_saas_core.py`, organization/discovery history/Saved/PDF tests, JavaScript regressions; evidence and status in `PHASE24_PROGRESS.md`.
- Dependencies: 24P.0 through 24P.5 completed and supported data contracts verified; an available real browser. Prior Phase 24S.2B.4 remains completed and must not be weakened or relabeled.
- Acceptance criteria: no confirmed unresolved security findings in changed scope; existing auth/tenant/company/viewer boundaries, stale guards, API compatibility, Saved, PDF and source failures pass regression. Real browser checks cover landing/auth/shell/Overview V2/Discover/company/PDF plus the approved rich command center at desktop/tablet/mobile widths, including all six KPIs, varied charts/widgets, sortable opportunities and filter/drilldown flows; keyboard navigation, focus, accessible chart alternatives and honest states pass. Measure actual render/update latency, payload size and layout behavior against a documented representative dataset and baseline; no unsupported performance claims. Record browser/tool limitations honestly; visual acceptance stays pending until checks run.
- Tests: targeted Python/JavaScript regression and relevant full offline suite; tenant/role/race/security cases; keyboard/accessibility checks and measured performance; real-browser responsive end-to-end flows for successful, empty, unavailable, partial/error and no-company states; `git diff --check`. Record actual outcomes without recycling older runs as Phase 24P evidence.

### Exact next single implementation task

24P.0 is fully completed with verified JS and focused/broader offline regressions. The next recommended task is 24P.1, the read-only audit of real analytics data and tenant scoping, when separately authorized. Milestones 24P.1-24P.6 remain PLANNED and were not started here. This checkpoint does not authorize commit, push, deployment or further external network/DNS/secrets operations.

PRODUCTION_TOUCHED=False
