# TenderLens AI v1.6.0

Status: release candidate preparation.

This document describes the intended v1.6.0 release content. It does not mean
that the Git tag, GitHub Release or production deployment already exists.

## Highlights

### Organizations and memberships

- Stable personal organization for registered Web accounts.
- Shared organization creation and membership management.
- Explicit `owner`, `admin`, `member` and `viewer` roles.
- Transactional authorization for protected organization mutations.
- Last-owner and personal-owner invariants.
- Legacy API key is not organization identity.

### Shared organization workspaces

- Organization-scoped company profiles.
- Shared active-company selection.
- Role-aware company mutations.
- Personal v1.5-compatible data remains separate and visible.

### Organization procurement workflows

- Shared active-company deterministic scoring.
- Organization-scoped on-demand EIS monitoring.
- Organization/company monitoring deduplication.
- Organization-isolated tender history.
- Organization-scoped PDF analysis and duplicate detection.
- Organization-isolated semantic RAG namespace.

### Invitations

- Invite existing or not-yet-registered users by email.
- High-entropy one-time tokens.
- SHA-256 token digests stored at rest.
- Expiration and revocation.
- Atomic acceptance and replay/concurrency protection.
- Browser invitation preview and authenticated acceptance flow.
- `Referrer-Policy: no-referrer` on invitation/auth pages that can carry the one-time token in the URL.

### Dashboard

- Personal/shared workspace selector.
- Shared organization creation.
- Member role management and removal.
- Invitation creation/list/revoke/copy-link UX.
- Role-aware writable/read-only controls.
- Personal v1.5 Dashboard data preserved.

## Compatibility

v1.6.0 keeps the existing personal/Telegram owner namespace for backward
compatibility. Shared organization resources use a separate organization
authorization boundary and internal reserved storage namespace.

The existing `v1.5.0` Git tag must not be moved or replaced.

## Security boundary

v1.6.0 implements application-level shared organization authorization, but the
supported deployment remains single-node and localhost-first.

Before broad public or multi-replica deployment, the project still requires:

- HTTPS/reverse-proxy hardening;
- PostgreSQL and migration tooling;
- Qdrant server/Cloud;
- distributed/edge throttling;
- structured audit events;
- operational retention, backups and secret rotation.

## Release-candidate validation

Completed locally for RC1:

- full regression: 279 passed, 1 skipped, 38 subtests passed;
- Python bytecode compilation and Compose configuration validation;
- isolated Docker health and embedded v1.6.0 verification;
- Web session, organization creation and invitation acceptance smoke;
- invitation replay/cross-origin/API-key boundary security smoke;
- SHA-256-at-rest invitation token verification;
- `Cache-Control: no-store` and `Referrer-Policy: no-referrer` verification for invitation/auth token-carrying pages;
- additive migration against a consistent copy of the current v1.5.0 production SQLite database;
- SQLite integrity and foreign-key checks after migration;
- byte-for-byte preservation of all original-column v1.5.0 rows;
- preservation of the existing account/session/Telegram link, AluTrade, active-company and monitoring state.

## Remaining release gates

Before publishing the final release:

- CI on the release pull request.

Tagging, GitHub Release publication and production deployment remain separate
explicit decisions after those checks pass.
