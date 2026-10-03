# Phase 18B ? Organization API + Transactional RBAC

Base commit: `21750cb` ? Phase 18A organization/membership foundation.

This phase exposes the first authenticated organization HTTP surface and
enforces role-based membership management without yet migrating tender,
RAG, monitoring, or company authorization away from legacy `owner_user_id`.

## Organization HTTP API

New session-authenticated endpoints:

- `GET /api/v1/organizations`
- `GET /api/v1/organizations/default`
- `POST /api/v1/organizations`
- `GET /api/v1/organizations/{organization_id}`
- `GET /api/v1/organizations/{organization_id}/members`
- `POST /api/v1/organizations/{organization_id}/members`
- `PATCH /api/v1/organizations/{organization_id}/members/{account_id}`
- `DELETE /api/v1/organizations/{organization_id}/members/{account_id}`

Organization endpoints require a real authenticated Web account/session.

Legacy `X-API-Key` access is deliberately not treated as an organization
identity and cannot independently authorize these endpoints.

## RBAC behavior

Roles remain:

- `owner`
- `admin`
- `member`
- `viewer`

Membership rules:

- owner and admin can manage ordinary memberships;
- admin cannot grant the owner role;
- admin cannot modify or remove an owner;
- owner can promote another member to owner;
- the final owner of an organization cannot be removed or demoted;
- the original owner of a personal organization cannot be removed or demoted;
- non-manager roles cannot enumerate or mutate membership through the manager API.

## Transactional security

Actor authorization and the membership mutation are performed under the
same SQLite `BEGIN IMMEDIATE` transaction.

This avoids a check-then-write race where an actor's role could change
between authorization and mutation.

Structural owner invariants are still enforced at repository level.

## HTTP security

Organization write endpoints reuse TenderLens same-origin browser-write
protection.

Explicit cross-site browser writes are rejected.

Responses containing organization/account membership data use
`Cache-Control: no-store`.

## Runtime integration

`ApiRuntime` now exposes `organization_service`.

Runtime initialization creates the organization repository against the
same SQLite database used by authentication.

Health component reporting includes the organization subsystem.

## Compatibility boundary

Phase 18B does NOT yet migrate business resources to organization scope.

The following existing areas still primarily rely on `owner_user_id`:

- company workspaces
- tender history
- PDF ownership
- semantic RAG ownership
- monitoring/subscriptions
- Telegram owner flows

That migration will be performed incrementally after this checkpoint.

## Validation

Focused organization/API suite:

`22 passed`

Auth/API/organization regression suite:

`40 passed`

Full suite:

`218 passed, 1 skipped, 38 subtests passed`

The remaining warning is the existing Starlette/httpx deprecation warning.

`compileall` passes.

`git diff --check` reports no whitespace errors; Windows may display
LF-to-CRLF working-copy warnings.
