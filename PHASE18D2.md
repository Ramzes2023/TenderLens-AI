# Phase 18D2 - Organization Scoring and Monitoring Context

Base commit: `ec34f1e` - shared organization active company context.

Phase 18D2 connects the shared active organization company to deterministic
scoring and on-demand EIS monitoring.

Background organization subscriptions are deliberately NOT introduced in this
checkpoint.

## Organization scoring

New session-authenticated endpoint:

- `POST /api/v1/organizations/{organization_id}/scoring/evaluate`

Scoring uses the organization's shared active company profile.

If one authorized member changes the active company, subsequent scoring by
other organization members immediately uses the new shared profile.

Viewer members may read/use scoring but cannot mutate the active company.

Legacy owner-based scoring remains unchanged.

## Organization monitoring

New session-authenticated endpoints:

- `GET /api/v1/organizations/{organization_id}/monitoring/status`
- `POST /api/v1/organizations/{organization_id}/monitoring/scan`

Monitoring status is readable by organization members.

On-demand monitoring scan is allowed to:

- owner
- admin
- member

Viewer remains read-only and cannot trigger organization monitoring scans.

Monitoring uses the shared active company profile for:

- dynamic EIS search terms
- pre-filtering
- company-specific monitoring context

## Monitoring dedup scope

Organization monitoring uses the reserved internal owner namespace:

`8_000_000_000_000 + organization_id`

The active company ID is also included in the monitoring dedup source scope.

This means:

- repeated scans for the same active company do not redeliver the same notice;
- changing to another active company gives that company its own monitoring
  context;
- organization monitoring state remains isolated from legacy Telegram/owner
  monitoring state.

The synthetic organization owner remains an internal compatibility/storage
namespace and is not an authentication identity.

## Transactional authorization

The external EIS fetch may happen outside the SQLite transaction.

Before organization monitoring dedup state is written, membership and role are
checked again inside the same SQLite `BEGIN IMMEDIATE` transaction as the
dedup write.

Therefore, if membership is revoked after fetch but before persistence, the
organization monitoring state is not written.

## Security boundaries

Organization workflow endpoints require authenticated Web sessions.

Legacy `X-API-Key` alone is not accepted as organization identity.

State-changing organization workflow requests retain same-origin browser
protection.

Cross-organization access is rejected.

## Compatibility

This checkpoint does NOT migrate:

- legacy Telegram monitoring subscriptions
- background organization notifications
- tender history ownership
- PDF analysis ownership
- RAG ownership/index namespace

Legacy owner-based scoring, monitoring and Telegram behavior remain available.

## Validation

Security-focused organization workflow regression:

`36 passed`

Full suite:

`239 passed, 1 skipped, 38 subtests passed`

The full suite was run twice successfully after the Phase 18D2 changes.

The remaining warning is the existing Starlette/httpx deprecation warning.

`compileall` passes.

`git diff --check` reports no whitespace errors; Windows may display
LF-to-CRLF working-copy warnings.
