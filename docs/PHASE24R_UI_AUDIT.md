# Phase 24R: placeholder and dead UI audit

Starting state: clean worktree on `phase24-professional-saas-core`, HEAD
`ce68ba6`. Audit preceded edits. This is a local product-quality cleanup,
without a redesign, deployment, commit, push, dependency installation or
changes to environment files, secrets or Monitoring matching.

## Surfaces and action paths inspected

Customer HTML is generated in `app/api`; there is no separate HTML template
directory. Inspected landing/auth/invitation/dashboard/shell/organization/
Telegram/Discover/Saved/History/Source Health/Support templates, all seven
external JavaScript files, all five shared stylesheets, page and API route
handlers, and existing UI contracts. Internal configuration names and test
fixtures were distinguished from customer copy.

| Surface | Audit outcome |
| --- | --- |
| Landing | All section hashes resolve; account and discovery links reach existing pages. Replaced the labeled illustrative procurement notice with actual workflow guidance. Billing teaser stays honest. |
| Login/Register | Form endpoints, password disclosure, account links and invitation return paths exist. Arbitrary server errors are no longer displayed; email/password validation and verification redirect remain intact. |
| Verify/Resend/Forgot/Reset | Existing APIs and generic delivery messages retained. Password-reset failures use professional status-based messages. No security or delivery semantics changed. |
| Invitation | Preview/accept/login/register/dashboard paths exist. Removed JSON error dumps and HTTP status text; corrected progress copy. |
| Shell/account/company switcher | All 15 navigation entries resolve to actual or honest future pages. Existing current-page and responsive behavior retained. Loading workspace state no longer prematurely enables onboarding. |
| Command palette | Navigation buttons are derived exclusively from sidebar destinations; no fake search or unsupported action commands found. |
| Dashboard | Existing Not run/session metrics are truthful. No fabricated KPIs found. Account and company names come from API state. |
| Discover | Search, filters, reset, detail, official source, save/remove and tender PDF analysis have existing paths. Fixed silent save/remove failures and hid mutation actions for read-only viewers. Errors appear inside open details as well as the page status. No procurement calls made in validation. |
| Saved Opportunities | Refresh/detail/remove/PDF actions exist and are scoped to the active shared company. Counts now distinguish unloaded/failure states from a real empty shortlist. Removal failures are visible inside the modal. Scope changes clear stale cards/counts. |
| Search History | Refresh/results/detail/close are real read-only archive actions. Counts and cards clear on workspace changes and remain unknown until fetched. No source re-query during history review. |
| Recommended | Explicitly unavailable; retains preliminary company-fit alternative and links to Discover. No invented recommendations. |
| Monitoring | Scan/status/refresh, role restrictions and seen-notice explanation retained. Corrected punctuation/loading text only. Matcher, sources, scan behavior and deduplication unchanged. |
| Source Health | Refresh reads recorded status without probing sources. Unknown counts never default to healthy/zero; scope transitions clear stale check timestamps. Removed internal exception-class names from failure cards. |
| AI Analysis | Standalone workspace explicitly unavailable; now directs users to actual tender PDF controls in Discover/Saved rather than implying the browser has no analysis workflow. |
| Documents | Existing analyzed-document list and reload use personal/shared stored-document routes. No invented standalone upload button added. |
| Companies | Create/activate/shared edit and company PDF preview/apply/discard have existing handlers/APIs. Removed named sample-company hints and the non-English product-keyword hint; retained useful generic field examples. |
| Team | Create/select/member roles/remove/invite/revoke/copy are backed by current routes. Replaced account-namespace and token implementation copy; corrected false clipboard-success reporting. Invitation links are no longer labeled one-time. |
| Notifications | Inbox explicitly unavailable, with configured personal Telegram alerts identified as the existing mechanism and Settings offered as the next step. No fake unread badge or inbox rows. |
| Billing | Billing/paid plans explicitly unavailable. No plans, subscription data, checkout or upgrade actions introduced. |
| Settings | Existing Telegram linking and recorded service-status controls retained. No fabricated connected or service-health defaults found. |
| Support | Launcher, report form, assistant, ticket list/conversations/replies and permission-gated operator controls map to current handlers/APIs. Fallback answers are labeled general guidance with AI unavailable; assistant overview no longer guarantees live availability. Conversation and submission errors avoid raw server payloads and native network exception copy. |
| Dialogs and states | Existing named dialogs and close controls retained. Fixed misleading unloaded counters, corrupt progress punctuation and failure feedback. Links remain navigation; mutations remain buttons; viewer mutation controls are omitted. |

## Exact findings and changes

- Landing contained a fabricated equipment tender, buyer, EUR 2.4M contract,
  18-day deadline, 84% fit and 72% completeness. It was labeled illustration
  only, so it did not claim to be production data; nevertheless removed all
  invented notice data and scores while retaining the existing panel layout.
- Discover Save/Remove silently reset buttons after failed requests. Added
  professional HTTP/network error feedback and retryable controls. Read-only
  viewers no longer see Save/Remove buttons that the server will reject.
- Saved removal errors were behind the open dialog. Added an accessible
  status within the shared detail renderer and displayed failures there.
- Saved/History/Source Health showed zero before a successful load and could
  retain another workspace's values. They now show Not loaded during initial,
  loading, reset and failure states; successful empty responses still show 0.
- Source Health displayed Python exception-class names and a stale last-check
  label after company transitions. Removed exception names and reset the label.
- Team displayed legacy namespace/version and raw-token implementation wording,
  and labeled invitation links one-time. Replaced it with private-account and
  link-sharing guidance. A failed clipboard fallback no longer reports copied.
- Company-name hints used AluTrade; one products hint was Russian. Replaced
  these with English, generic guidance. Legitimate generic field examples and
  developer/test fixture data remain.
- Loading, accepting, saving, applying, scan separators and a missing-data
  label contained literal question marks as damaged punctuation. Corrected
  these without changing matcher or analysis behavior. Support close uses ×.
- Shell compared inconsistent loading labels and could reveal onboarding
  while loading. It now recognizes both existing loading text variants.
- Future-page default copy referred to the next phase. Removed the implied
  scheduling promise; all future destinations explicitly say unavailable.
- AI Analysis copy overlooked the current Discover/Saved PDF upload workflow.
  Corrected that guidance and added only links to existing supported pages.
- Support fallback answers could resemble live AI answers. They now explicitly
  identify AI unavailability and general product guidance. Arbitrary server
  errors are not rendered in conversations, ticket submission or auth forms.
- Invitation errors could serialize validation objects or server details.
  Replaced that with status-based customer guidance and connection feedback.
- Public health data returned TenderLens AI. Corrected the service display
  value to VALYQON AI. Document-storage failures in personal document APIs
  now return a professional message rather than raw database exception text.
- No bare `href="#"`, `javascript:void(0)`, fake payment controls,
  testimonials, notification rows, recommendation cards, or visible
  TODO/FIXME/TBD were found in generated customer HTML. Existing destinations
  and real action controls were preserved; no backend feature invented.

## Intentional future state and deferred work

Recommended, Notifications, Billing and the standalone AI Analysis workspace
remain honest unavailable destinations. Discover/Saved tender PDF analysis,
company PDF profile drafting and the real support assistant remain supported
actions whose providers can be unavailable; no fake analysis is supplied.
Automatic procurement-document import, recommendation engine, team notification
inbox, paid plans/payments, standalone analysis workspace and scanned-PDF OCR
remain deferred. The old Monitoring matcher issue remains deferred unchanged.
Phase 24S.1, PostgreSQL, Redis, workers, AI Gateway, Supplier Intelligence and
Phase 25+ were not started.

The real configured Telegram destination remains `TenderLensAI_bot`. This is
an external bot identity, not visible product branding; renaming the URL without
a real replacement would break linking. A bot identity migration requires a
separate product/operations decision. Internal cookie/configuration/module/
repository/database names remain compatible. No other product decision blocks
this cleanup. Browser visual review on mobile and with real populated customer
data remains a manual acceptance step, not a claimed automated result.

## Validation

Changed external JavaScript assets (shell, Discover, Saved, History, Source
Health and Support) consistently use `v=phase24r`. Unchanged CSS and premium
JavaScript versions remain unchanged. Affected asset contracts were updated.

New focused tests inspect generated customer HTML (excluding scripts/styles
from copy checks), all navigation mappings/hashes, future-state honesty,
unloaded counts, error-copy protection and changed cache versions. Node tests
execute the actual shell/palette/Discover handlers with mock browser objects
and requests, covering all 15 destinations, current highlighting, future next
links, failed save/remove retry, viewer controls and clipboard fallback.
The existing Discover browser harness now supplies the current location and
role contracts; no fixtures are scanned for prohibited customer words.

Validation uses the existing Python virtual environment and existing Node
runtime, with `VALYQON_EMAIL_MODE=disabled`, dotenv loading blocked and external
socket connections rejected. No dependencies installed, emails sent, AI calls,
procurement calls, production traffic or deployments. Test doubles and temporary
SQLite test databases only. Final targeted results and diff-check recorded below.

- Main targeted suite: 230 passed, no skips, exit 0. Covers responsive UI,
  dashboard, auth/verification/reset, companies/onboarding/company PDF,
  Discover/history/shortlist behavior, Saved, Monitoring UI contracts,
  Source Health, Support, organizations/invitations, document PDF/RAG and
  Phase 24R contracts. Matcher tests were not run or modified.
- Follow-up suite: 15 passed, exit 0 (all 14 Phase 24R cases plus the newly
  added document-storage error regression). Across both successful runs,
  231 distinct Python test cases passed.
- Existing Node shortlist and full-AI rendering tests: both PASS, exit 0.
  Existing Discover and company browser tests passed in the main suite;
  Phase 24R shell/palette/shortlist/copy behavior passed in both suites.
- `node --check` on modified Discover and Support: exit 0.
- `git diff --check`: exit 0. HEAD remains `ce68ba6`.
- Existing Starlette/httpx deprecation warning remains. No dependency change
  made to resolve it. No browser visual screenshots claimed.

The first validation run exposed the existing broken missing-data separator
and outdated Discover harness browser context, which previously skipped when
Node was not on PATH. Customer punctuation and the test harness were corrected;
the successful rerun includes those tests. This was unrelated to Monitoring.

## Files changed

Product:

- `app/api/auth_pages.py`
- `app/api/dashboard.py`
- `app/api/history_ui.py`
- `app/api/invitation_page.py`
- `app/api/landing.py`
- `app/api/organization_ui.py`
- `app/api/routes.py`
- `app/api/saas_shell.py`
- `app/api/saved_ui.py`
- `app/api/source_health_ui.py`
- `app/api/static/discovery.js`
- `app/api/static/history.js`
- `app/api/static/saved.js`
- `app/api/static/shell.js`
- `app/api/static/source_health.js`
- `app/api/static/support.js`
- `app/api/support_ui.py`

Contracts and regression tests:

- `tests/js/discovery.test.cjs`
- `tests/js/phase24r.test.cjs` (new)
- `tests/test_api.py`
- `tests/test_monitoring_ui_contract.py`
- `tests/test_phase24r_ui_audit.py` (new)
- `tests/test_premium_ui.py`
- `tests/test_saved_ui_contract.py`
- `tests/test_search_history_ui_contract.py`
- `tests/test_source_health_ui_contract.py`

Documentation: `docs/PHASE24R_UI_AUDIT.md` (new).
