# Phase 24 Professional SaaS Core

## Starting point
Clean phase23-global-sources-wave1 at ac6e69d7a94ded7e67b81a8ee5537619d27b0fa5.
Development branch: phase24-professional-saas-core.

## Completed
Checkpoint 2: real shared-organization discovery, local filters, metadata cards, source
health, detail dialog, safe source links, separate fit/completeness and honest AI states.
Abort/epoch checks reject late discovery and API responses on workspace changes.
Checkpoint 1: public landing with session-aware CTA, responsive authenticated navigation,
existing organization/company/team controls retained, truthful future pages and local assets.

## In progress
Company onboarding and profile refinements.

## Not started
Richer company onboarding, final regression and push.

## Files changed
app/api/landing.py, saas_shell.py, static/saas.css and shell.js: presentation.
app/api/dashboard.py: wraps existing HTML; main.py: local /assets mount.
app/api/routes.py: public root now returns landing HTML.
tests/test_saas_core.py and test_branding.py: shell/assets/branding regression.

## Backend/API changes
GET / returns no-store landing HTML, session-aware CTA. /assets serves local static assets.
Discovery response adds optional published_at and summary from the existing notice model.
No source adapters, authorization, scoring or seen-state behavior changed.

## Frontend changes
Landing and dashboard sidebar, responsive menu, workspace selector, feature placeholders.

## Tests
21 shell tests passed; 26 integration/security tests passed. New Node regression
checks rendering, filters, unsafe links, partial/total failures and stale responses.
Full regression pending. git diff --check clean.

## Git commits
2cc6605 — Build professional VALYQON SaaS shell.
Checkpoint 2 — Add global tender discovery workspace (hash recorded next checkpoint).

## Known issues
Discovery endpoint requires organization-scoped company data, distinct from legacy
personal profiles. UI must explain this and guide users to a shared organization.

## Exact next step
Extend existing company form with supported markets/currencies/search fields and shared
company editing; preserve hidden profile fields; run targeted and full regression.
