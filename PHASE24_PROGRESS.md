# Phase 24 Professional SaaS Core

## Starting point
Clean phase23-global-sources-wave1 at ac6e69d7a94ded7e67b81a8ee5537619d27b0fa5.
Development branch: phase24-professional-saas-core.

## Completed
Checkpoint 1: public landing with session-aware CTA, responsive authenticated navigation,
existing organization/company/team controls retained, truthful future pages and local assets.

## In progress
Discover workspace and company-context wiring.

## Not started
Discovery results/detail/filtering, richer company onboarding, final regression and push.

## Files changed
app/api/landing.py, saas_shell.py, static/saas.css and shell.js: presentation.
app/api/dashboard.py: wraps existing HTML; main.py: local /assets mount.
app/api/routes.py: public root now returns landing HTML.
tests/test_saas_core.py and test_branding.py: shell/assets/branding regression.

## Backend/API changes
GET / returns no-store landing HTML, session-aware CTA. /assets serves local static assets.
No source, auth, company, scoring, monitoring or discovery API logic changed.

## Frontend changes
Landing and dashboard sidebar, responsive menu, workspace selector, feature placeholders.

## Tests
21 targeted tests passed; full regression pending. git diff --check clean.

## Git commits
Checkpoint 1: Build professional VALYQON SaaS shell (hash recorded next checkpoint).

## Known issues
Discovery endpoint requires organization-scoped company data, distinct from legacy
personal profiles. UI must explain this and guide users to a shared organization.

## Exact next step
Implement Discover using the existing organization endpoint, with stale-response rejection
on organization/company switches, then test metadata wording and partial failures.
