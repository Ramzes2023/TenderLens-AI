# Phase 24Q responsive UX

Starting state verified: clean worktree, branch `phase24-professional-saas-core`,
HEAD `60b3e50`. Local changes only; no deployment, commit, push or dependency install.

## UI audit and implementation

The application renders Python HTML templates and shared CSS/JavaScript, without
a frontend framework or an installed browser testing framework.

| Existing surface | Responsive treatment |
| --- | --- |
| Global shell, navigation, account menu, company/organization context | Preserve desktop sidebar above 1050px; disclosure navigation in document flow below it, with scrollable menu, current-page focus and Escape focus return |
| Dashboard, onboarding, KPI cards | Intrinsic grid sizing, compact phone typography, single column on narrow phones |
| Discover, Saved, Search History, Source Health | Existing shared tender cards and lists retained, metadata and long titles wrap; filters stack; action buttons wrap without losing actions |
| Companies, create/edit, PDF profile assistant, switcher | Full-width bounded inputs, stacked form grid, touch-sized controls, long names wrap |
| Monitoring | Status grid and action rows reflow; matching/backend behavior untouched |
| Tender detail, full PDF AI analysis, analyzed document list | Existing upload/actions retained, file controls bounded, filename/AI output wrapping, stacked scoring/details |
| Team, members, invitations, Settings/Telegram, account menu | Shared form/action/long-text primitives; invitation acceptance also loads responsive styles |
| Support requests, assistant, conversations, operator controls, launcher | Intrinsic sizing, stacked conversation layout, wrapped headers/actions, bounded short-screen panel/chat |
| Login, register, verify email, forgot/reset password | One existing scalable viewport per page, shared mobile padding, readable hints/errors, full-width inputs and touch targets |
| Tender/history/saved dialogs and command palette | Viewport-bounded scrolling, sticky title/close row, stacked content |
| Public landing page | Shared stylesheet, narrow-screen heading sizing and existing real CTA remains available |

No customer-facing HTML tables or pagination controls were found in the templates
or JavaScript renderers. Existing card/list representations are retained; no table
conversion or invented interactions were added. AI Analysis, Recommended, Billing
and Notifications retain their existing availability/future-state messaging.

The new shared stylesheet loads last and uses only 1050px, 760px and 420px
breakpoints. Existing premium design tokens and branding remain in use. Overflow
is handled by intrinsic sizing and wrapping rather than hiding page overflow.

## Validation

33 new structural tests cover viewport uniqueness/scaling, shared stylesheet
inclusion/order, reachable navigation, required workflow controls, auth labels,
PDF actions, named dialogs, asset serving and existing card/list structure.
Existing web/auth/company/discovery/shortlist/PDF/monitoring/support/source-health
tests are also run. Email is disabled and dotenv loading is blocked in the local
test runner; providers and procurement sources use existing test doubles.

Final targeted result: 188 tests collected, 186 passed, 2 skipped (existing
Node-based regression tests; Node is unavailable), exit 0. `git diff --check`
also exits 0. The existing Starlette/httpx deprecation warning is unchanged.

Manual visual validation remains required at 320px, 375/390px, 768px, 1024px,
1280px and desktop widths, plus short landscape viewports and 200% zoom:

- Open/close menu, follow current and different links, keyboard focus/Escape,
  resize across the desktop breakpoint, and reach every navigation group.
- Dashboard with and without a company; very long company/organization names.
- Discover filters and populated cards, Saved, History, Source Health and
  Monitoring status/error/loading/empty states with long titles/identifiers.
- Company create/edit/onboarding and Team invitation/member controls.
- Tender and company PDF selection with long filenames; mocked analysis results
  with long evidence, citations and URLs; dialog close controls while scrolling.
- Support forms/conversations and launcher in a short viewport.
- All five auth pages and invitation acceptance; native password/file/date/select
  controls on iOS Safari and Android Chrome, including virtual keyboard behavior.
- Desktop appearance and interactions against the starting revision.

No browser visual checks have been claimed. Node-based existing tests may skip
when Node is unavailable; no dependencies are installed to replace them.
