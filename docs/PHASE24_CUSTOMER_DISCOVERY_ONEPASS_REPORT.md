# Phase 24 customer discovery product milestone

Date: 2026-10-13. Existing worktree retained; no git writes, backend changes, provider probes, database access, LLM calls, dependency installation or deployment.

CUSTOMER_DISCOVERY_PRODUCT_CHANGE=YES

P3.9=BLOCKED

## Existing behavior retained

The application already had the company PDF proposal/review/explicit Apply flow and optional navigation to Discover; shared organization/company selection; explicit discovery POST; metadata preview scoring in its response; local result filters; detail criteria/evidence; authoritative tender PDF analysis; company-scoped shortlist APIs and Saved page; and separate Monitoring and Source Health surfaces. These were reused. Discovery does not need a second `/scoring/evaluate` request to display preliminary fit: the existing discovery response already contains that result. No second dashboard, scoring pipeline or monitoring workflow was added.

Inspected `discovery_ui.py`, `discovery.js`, `dashboard.py`, `saas_shell.py`, `shell.js`, `locale.js`, `premium.css`, `premium.js`, `saved.js`, schemas, organization workflow contracts and source catalog (read only). Existing Origin/membership checks and API contracts remain intact. Existing operational content remains English with shell-owned EN/RU data bindings for added journey/decision labels.

## Product implementation

| Path | Incremental change in this run |
| --- | --- |
| `app/api/discovery_ui.py` | Guided decision panel, company/PDF profile review link, Saved and Monitoring handoff links; live guide status and per-source outcome container. |
| `app/api/static/discovery.js` | `updateGuide` reflects active company, organization ID, actual loaded search keywords, loading, results, empty, total failure and preview unavailability. `decisionHtml` surfaces score reasons, stop factors and unknowns directly on cards and detail, with conservative absence language. `sourceOutcomes` renders returned states, counts, auth requirements and messages/errors without generating availability. `officialUrl` permits only exact catalog HTTPS hosts, without credentials or alternate ports, on cards and detail. Save/remove handlers enforce current write role, shared active company and preview/loading guards. Repeat searches close/clear detail and invalidate shortlist reads; save/remove and saved PDF snapshot completions now also check discovery generation. Null fit/completeness no longer becomes zero during ranking. |
| `app/api/static/premium.css` | Focused wrapping, outcome grid, narrow-screen filters/detail and link focus treatment. Existing styling retained. |
| `app/api/saas_shell.py` | Changed only Discover script version to load this product update. Other existing uncommitted shell work retained. |
| `tests/js/main_customer_discovery_flow.test.cjs` | New seven-group deterministic browser-script behavioral suite. |
| `tests/test_customer_discovery_contract.py` | New static HTML/JS wiring contract, independent of backend imports and DB. |

Measurable changed behavior and passing tests: `decisionHtml`/`sourceOutcomes`/`officialUrl` → explicit-click/partial-outcome/criteria/XSS/official-link group; `updateGuide`/`discover`/`reset` → company-switch, empty/failure/preview groups; `saveItem`/`removeItem` → permitted Save/Remove and forged role-downgrade group; generation guards in `discover`/`saveItem` → repeat-search and denied/late-Save groups. The guide uses existing shell localization data attributes, rather than adding a competing locale state or event consumer.

## Actual verification executed

Node/Python were unavailable through shell PATH and the searched runtime locations. An available Node REPL was then discovered and used against the actual workspace files. No runtime installation was needed.

**New behavioral suite: PASS, seven groups**, executing the shipped `discovery.js` through classic-script global bindings with real Node URL/AbortController. Fetch is the network boundary mock; application functions, renderers, filters and installed click/context handlers run unchanged. A minimal DOM harness records rendered HTML and dispatches events; this is not a full browser engine or visual QA.

1. Explicit Find click, loading disablement, existing authenticated POST, partial source outcomes including transport failure and auth-required source, visible preliminary score/reasons/unknowns, XSS escaping, exact official HTTPS links on card/detail, and no automatic scoring/monitoring calls.
2. Company-switch abort, cleared results/source outcomes, no old company result flash, including change while response JSON is pending.
3. Permitted Save and Remove use existing shortlist endpoints; Saved state appears; current role downgrade blocks previously rendered controls and forged viewer actions.
4. Repeat search closes/clears detail and discards an older Save completion.
5. Denied Save returns to retryable state; company-switch discards late Save UI updates.
6. Empty, total source failure, 503/unavailable, 403, 409, 401 redirect, private workspace and API-disabled port 8765 states.
7. Actual local filter input/reset handlers, conservative missing-data defaults and preliminary versus full document score labels.

**Existing suites: PASS**, evaluated in isolated Node VM contexts with captured logs, awaiting asynchronous checks and inspecting exit status:

- `main_discovery_scoring_monitoring.test.cjs`: honest labels and cross-company stale isolation.
- `main_live_discovery_contract.test.cjs`: honest labels and cross-company stale isolation.
- `main_pdf_to_discover.test.cjs`: explicit Apply, optional navigation, role/scope/preview guards and card contrast.
- `main_pdf_ai_ux.test.cjs`: document hub, permissions, preview isolation and PDF contracts.
- `main_i18n.test.cjs`: shell coverage, switching, persistence, context, safe text, keyboard and English page boundaries.

**Additional checks: PASS** — Node JS compilation; unique markup IDs; required journey/result/detail IDs; company/Saved/Monitoring handoff links; `git diff --check` on the four edited product files (exit 0, existing line-ending warnings only).

An initial new-suite execution exposed a selector reference error introduced during editing; fixed and rerun. The existing localization suite initially rejected Discover's direct locale coupling; fixed by using the existing shell data-binding ownership and rerun successfully. No existing test was edited.

**Python contract: NOT EXECUTED.** Actual attempt through Node child process: `python -B -m pytest -p no:cacheprovider tests/test_customer_discovery_contract.py -q` → `spawn python ENOENT`. An early alternate orchestration-V8 attempt also could not run browser globals (`URL` unavailable); it is not counted as verification. Host launcher must run the Python contract. Standard host commands:

```text
node tests/js/main_customer_discovery_flow.test.cjs
python -B -m pytest -p no:cacheprovider tests/test_customer_discovery_contract.py -q
```

## Browser review sequence (not executed here)

1. Open the authenticated application, select a shared organization, and activate an existing company as owner/admin/member. Open Companies, use its existing company PDF assistant, review the proposal and explicitly Apply. Use the optional Discover navigation. Confirm the guide names the active company and actual loaded keywords. Nothing should auto-search.
2. Click Find opportunities. Confirm loading clears previous cards/detail, disables repeat Find, then shows returned source outcomes and cards or an accurate empty/failure state. Counts refer to fetched results, never total market coverage.
3. Review card reasons, stop factors and unknowns. Confirm absent value/currency/deadline is not invented. Open the HTTPS official source and detail criteria/evidence. Preliminary Match must remain metadata-only until an explicit tender PDF analysis yields document-backed scoring.
4. Save one candidate. Confirm Saved state; follow Review saved opportunities to the existing Saved workspace for that company. If save is denied/unavailable, verify the actionable error and retry control.
5. Follow Open monitoring controls. Inspect existing monitoring status. Run a scan only via its existing explicit permitted scan control. The Discover handoff must neither scan nor subscribe. Saving an opportunity is not a per-notice monitoring subscription.
6. While Find is in flight, switch company or organization. Confirm old cards, source outcomes and detail disappear before any late response; only an explicit new Find can populate the new discovery scope. Repeat Find while an older Save is pending and check that its completion cannot repaint the new search.
7. Review as viewer: search/read behavior stays under existing membership contracts; write controls are absent and forged Save/Remove calls do not issue requests. Review laptop/mobile wrapping and keyboard focus manually.
8. Switch EN/RU: navigation and added bilingual journey/decision labels follow shell affordance; original operational fields, source payloads and forms retain the English module boundary. On safe preview port 8765, Find is disabled with explicit API-unavailable guidance.

## Evidence and remaining blockers

No live authenticated browser session, screenshot, browser layout signoff, refreshed source availability, real customer fit or end-to-end backend signoff is claimed. All test notices/companies/scores are explicit synthetic fixtures used only at the mocked network boundary.

Prior evidence remains historical and unchanged: `PUBLIC_LIVE_TED_GATE=VERIFIED`; `REAL_NOTICE_SYNTHETIC_PROFILE_SCORING=VERIFIED; EVALUATIONS=5`; `LIVE_TO_SCORING_OFFLINE_GATE=PASS`. Those refer to prior genuine TED notices on the Windows host and synthetic-company preliminary scoring; this run did not refresh them. UK Find a Tender previously failed with `ConnectorTransportError`; SAM.gov requires an auth key. New source outcomes describe only the current backend response, including disabled/not-checked states, never promised coverage.

Host Python regression execution and real authenticated browser/backend review remain outstanding. Existing full document analysis requires its real backend and explicit upload, and was preserved rather than live-tested. Official outbound links fail closed for unknown sources/hosts; future official hostname changes require review of the small UI allowlist. Regional Russia/CIS work and all source adapters were untouched. P3.9 production gate stays BLOCKED.
