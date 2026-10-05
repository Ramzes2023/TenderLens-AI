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

- Saved opportunities service
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

- `2cc6605` — Build professional VALYQON SaaS shell
- `f1a4958` — Add global tender discovery workspace

Final company/onboarding/polish checkpoint is represented by the current Phase 24 finalization commit.

## Known issues

- Real browser visual/mobile review remains pending.
- Existing Starlette TestClient/httpx deprecation warning remains; it does not fail the suite.
- Future product sections intentionally remain placeholders where corresponding backend services do not yet exist.

## Exact next step

After this checkpoint is committed and pushed:

1. Perform a real browser visual review of landing, dashboard, Discover, tender detail and company onboarding on desktop and mobile widths.
2. Fix only genuine visual/usability defects found during that review.
3. Then close Phase 24 and begin the next product phase.

Do not deploy Phase 24 to production as part of this checkpoint.
Do not add procurement sources.
Do not resume the abandoned TED document experiment.

PRODUCTION_TOUCHED=False