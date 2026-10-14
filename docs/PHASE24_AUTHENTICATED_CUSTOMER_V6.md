# Phase 24 V6 — isolated customer journey

V6_CODE_CHANGES=YES
API_E2E=NOT_VERIFIED
BROWSER_AUTHENTICATED=NOT_VERIFIED
LIVE_TED_PRIOR=5_NOT_REPROBED
V6_REAL_TED_IN_THIS_RUN=NO
P39_PRODUCTION_GATE=BLOCKED
HOST_EXECUTION_REQUIRED=YES

Delivered a reproducible layered acceptance harness, two synthetic company profiles,
and new Python/DOM acceptance tests. No Python, Node, authenticated API, Chromium,
or public HTTP execution occurred in this Codex run. This is source delivery for a
local acceptance milestone; it does not complete the authenticated integration gate.

## Exact changes and checks

Four new allowlisted files only:

- `scripts/phase24_v6_customer_browser_acceptance.py`: required `--offline --report
  <json-path>` CLI, unique synthetic accounts/company names, disposable SQLite
  factory cleanup in `finally`, real verification/login routes, fixture procurement
  transport, two-profile scoring matrix, scoped Save/list and negative checks.
- `tests/test_phase24_v6_customer_journey.py`: nine planned parametrized test cases
  using existing real modules and factories; no executed pass count yet.
- `tests/js/main_phase24_v6_customer_journey.test.cjs`: pure renderer/filter/link
  assertions plus the existing seven behavioral DOM groups executing the shipped
  Discover handlers. This is a minimal DOM, not Chromium or session proof.
- `docs/PHASE24_AUTHENTICATED_CUSTOMER_V6.md`: evidence and repeat instructions.

No existing source file changed in V6. Existing modifications were present before
this run and preserved, including changes outside this milestone's allowlist.
No migrations, auth/security/session implementation, billing, configuration,
environment files, existing containers, port 8765, or other worktree were changed.
Branch observed: `phase24-professional-saas-core`.

Execution evidence: `where.exe python` and `where.exe node` found no executables.
`where.exe docker` resolved a workspace entry, not a verified Docker engine; it
was not executed. No disposable PostgreSQL container was created. The absence of
Python prevents running the application factory or browser bindings here.
`git diff --check` is the only executable source validation performed (see final
result below). Tests remain pending host execution; no invented scores or PASS.

## Journey trace and integration boundary

The existing `/login` browser flow calls `POST /api/v1/auth/login`. AuthService
checks the password and email verification, then the route issues the HttpOnly
session cookie. `/api/v1/auth/me` resolves that session. The shipped dashboard
and shell share organization selection, active-company state and workspace
context events; company activation uses the organization-scoped company routes.

`discovery_ui.py` is included in `saas_shell.py`; shipped `discovery.js` installs
the explicit Find handler. Loading the Discover view must not retrieve tenders.
Find sends `POST /api/v1/organizations/{id}/discover/tenders`. The backend resolves
real session membership and the authorized active company, calls SourceCatalog
and the monitoring prefilter, then maps notices through `analysis_from_notice`
and `score_metadata_preview`. Source outcomes distinguish partial/total failure
and empty success. The backend rechecks company/profile/membership after fetch.

Cards/detail show Metadata preview, category evidence, unknown values and stop
factors. Official links use canonical source hosts, HTTPS, and no credentials;
the DOM tests check escaping and `noopener noreferrer`. Metadata fit is not Full
Document Match, verified eligibility, or likelihood of winning. Missing amount,
deadline and document facts stay unknown; no FX conversion is fabricated.

Save sends the scoped `/shortlist` POST with preview provenance. The backend
checks company/profile/organization context; storage checks write rights. Saved
navigation is `#saved` in the existing shell and its existing `saved.js` lists
the scoped shortlist. The new API layer exercises the actual list endpoint;
neither browser navigation nor the Saved DOM has been executed in V6.

The supported isolated factory is `OrganizationWorkflowTests.setUp` in
`tests/test_organization_workflows.py`. It explicitly constructs AuthRepository,
OrganizationRepository, CompanyRepository and MonitoringRepository on a fresh
temporary SQLite file, passes ApiRuntime and ApiSettings into `create_app`, and
registers cleanup. V6 wraps the factory's existing register/create hooks to use
unique run identities and a random password held only in memory. It obtains
verification tokens from the existing AuthService method and consumes them through
the real verify-email route. Login then uses the real password route; V6 never
uses the factory's cookie-injection helper. No email sender is attached.

Before import, dotenv and the module-level settings loader are replaced in the
test process. The explicit runtime prevents configuration/real DATABASE_URL use;
`build_runtime` is guarded against accidental calls. Actual HTTPX network
transports fail closed. Adapter transports are explicit MockTransport instances,
so no DNS or public HTTP is necessary. Windows asyncio's internal socketpair is
left intact. No auth/RBAC dependency is overridden.

Saved uses the existing V5 ScopedMemorySaved double, which calls real organization
and company authorization services. This is **not production SQL persistence**.
Even a successful harness run records `layered_api=PASS` separately and leaves
`API_E2E=NOT_VERIFIED` and `BROWSER_AUTHENTICATED=NOT_VERIFIED`. Missing Python
modules produce a NOT_VERIFIED layer; assertions produce FAIL with a check label.
No fake browser login, screenshot, trace, browser PASS, or persistent staging
server is produced. Optional installed Node runs only the minimal DOM script.

Full integration requires an executable Python environment, verified Docker
capability for a fresh ephemeral PostgreSQL runtime, and already installed
Playwright/Chromium. Any later PostgreSQL harness must create its own uniquely
named container with memory-only random credentials, random localhost-only host
port, no host volume, and finally cleanup. It must not discover or reuse existing
database URLs/containers. A browser runtime must use a separate isolated port,
never 8765; screenshots/traces belong under TEMP only. Those capabilities were
not verified in this run, so this delivery deliberately uses the permitted
layered alternative and needs no credentials or software installation.

## Fixture evaluation and evidence counts

Every synthetic notice title and report is labelled **OFFLINE_FIXTURE**. There
are six input records representing five distinct identities, including a duplicate.
The actual TED parser deduplicates them. Two distinct profiles produce ten planned
metadata evaluations, calculated by the existing scoring module, not hardcoded:

- Industrial cable supplier accepts RON/EUR. Cable notices supply positive
  category evidence; accounting/furniture are negative. A cable notice with
  missing amount/deadline remains unknown. Another with USD must retain the
  currency failure and stop factor even when category evidence is positive.
- SaaS accounting vendor accepts EUR. Accounting subscription supplies positive
  category evidence; cable/furniture notices are negative. Documents remain
  unscored because no full tender documents are supplied.

The JSON report contains actual matrix criterion explanations/evidence, unknowns,
stop factors and calculated scores **only after execution**. No numeric score is
claimed in this document. Fixture URL formats are not observed public notices and
are not presented as verified links. `real_results_count=0`, `outbound_calls=0`.

Historical host V5 evidence supplied by the owner: five real TED notices,
zero matches versus the synthetic profile. This is `5_NOT_REPROBED`; no historical
JSON was available through a specifically identified local path in this audit,
so V6 uses deterministic synthetic fixtures and does not relabel replay as live.
UK FTS 503 is a deliberate offline transport failure, not a fresh availability
measurement. SAM.gov is not attempted. No buyer contact, registration, submission,
automatic bid or contract-win claim occurs.

## Repeat without a real database

From the repository on the host, with the launcher's existing dotenv withholding
and deliberately unusable DATABASE_URL:

```powershell
python -m pytest -q -p no:cacheprovider tests/test_phase24_v6_customer_journey.py
node tests/js/main_phase24_v6_customer_journey.test.cjs
python scripts/phase24_v6_customer_browser_acceptance.py --offline --report "$env:TEMP\phase24-v6-customer.json"
```

The CLI requires a JSON output path, emits the seven requested V6 status lines,
and additionally reports `V6_LAYERED_API`. Exit 1 means a failed check or missing
Python capability; exit 0 means completed available layers, **not browser/API_E2E
acceptance**. Read `dom_script` and blockers for unavailable Node. Temporary
SQLite storage is removed by the existing factory's cleanup, even on failure.
The JSON report contains no password, verification token, cookie or account email.

Preserve previous acceptance coverage:

```powershell
python -m pytest -q -p no:cacheprovider tests/test_phase24_customer_acceptance.py tests/test_organization_workflows.py tests/test_shortlist_api_behavior.py tests/test_phase24_live_discovery_contract.py tests/test_phase24_live_to_scoring.py tests/test_pdf_discovery_scoring_monitoring_e2e.py
node tests/js/main_phase24_customer_acceptance.test.cjs
git diff --check
```

No live-probe command is part of V6. Host execution must append actual results
before claiming any new gate. Remaining blockers: Python/Node execution,
PostgreSQL Saved persistence, real authenticated browser login/Find/detail/Save/
Saved navigation, and browser permission/context-switch evidence. P3.9 is BLOCKED.

Final source validation: `git diff --check` executed, exit 0. Git emitted existing
LF/CRLF warnings. This validates whitespace, not Python/JS syntax or behavior.
