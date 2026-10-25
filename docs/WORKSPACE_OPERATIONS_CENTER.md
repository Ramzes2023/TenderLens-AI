# VALYQON authenticated Operations Center — product acceptance

An interactive redesign of the existing permission-checked dashboard,
not a separate procurement engine or a simulated tenant dataset.

## What is implemented

- Four honest account-context indicators: selected organization, active company,
  browser-session Discovery returned rows, last loaded Saved company count.
  Unknown indicators say 'Not run', 'Not loaded', or show an em dash.
- A verified 3-step checklist: shared organization, active company, and
  Discovery attempted. An attempt is never equated with an operational source.
- Context-aware next-step link pointing only to Team, Companies, or Discover.
- Pinned page links using allowlisted route names in localStorage (up to six).
- Recently visited page links using allowlisted route names in sessionStorage
  (up to five). These are UI history, never tender or company activity records.
- Functional Pin / Unpin control with aria-pressed, Ctrl+K existing page
  navigation, and '?' guide using an accessible native dialog.
- Dark enterprise accent panels, rich cards, responsive layouts and optional
  reduced-motion styling; no new APIs, permissions, scans, background jobs,
  alert dispatch, bidding process or sample tenders.

## Browser acceptance (isolated port 18865)

1. Sign into the local-only website preview and open Overview.
2. Confirm new metrics never show imaginary market totals in an empty database.
3. Switch account workspace / company: update progress and next action.
4. Visit Discover, Saved, and Monitoring; return to Overview, inspect
   the recently visited links and pinned shortcuts. Pin and unpin a route.
5. Press '?' outside any text box: the guide appears. Esc closes it.
   Typing '?' in search fields must not open the guide.
6. Use the RU/EN switch and verify translated headings and live statuses.
7. Check desktop, tablet and mobile sizes, including the separate scrolling
   navigation and active-company footer.
8. If an optional source service is down, preserve verified organization
   context and show a truthful degraded state, not fake operating status.

## Backend-dependent features deferred

Tenant-scoped tender deadline calendar, real-time source uptime history,
verified alerts, team task assignments, opportunity kanban board and richer
company analytics require real persisted data, authorization, worker proof
and tests; these are not advertised as completed in this PR.
Do not merge before final CI, in-browser retest and independent
source-to-worker-to-database-to-user acceptance.
