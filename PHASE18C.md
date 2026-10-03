# Phase 18C ? Organization-Scoped Shared Company Workspaces

Base commit: `c664e7c` ? Phase 18B Organization API + transactional RBAC.

Phase 18C introduces shared company workspaces whose security boundary is
`organization_id` rather than an individual legacy `owner_user_id`.

## Organization company API

New session-authenticated endpoints:

- `GET /api/v1/organizations/{organization_id}/companies`
- `POST /api/v1/organizations/{organization_id}/companies`
- `GET /api/v1/organizations/{organization_id}/companies/{company_id}`
- `PATCH /api/v1/organizations/{organization_id}/companies/{company_id}`
- `DELETE /api/v1/organizations/{organization_id}/companies/{company_id}`

These endpoints require a real authenticated account/session.

Legacy `X-API-Key` is not an organization identity.

## Company RBAC

Organization roles:

- owner: read, create, update, delete
- admin: read, create, update, delete
- member: read, create, update
- viewer: read only

Authorization and organization-scoped company writes are performed inside
the same SQLite transaction for mutation operations.

## Shared storage

`company_workspaces.organization_id` is now used as the shared workspace
security scope.

Members of the same organization can access the same organization company.

Companies from another organization are not visible even when their numeric
company IDs are known.

Organization company names are unique within one organization.

## Legacy isolation

Existing owner-based company APIs remain available for v1.5 compatibility.

Shared organization companies use a reserved compatibility owner namespace:

`8_000_000_000_000 + organization_id`

This synthetic `owner_user_id` is not the authorization boundary.

The legacy owner-based repository rejects or hides the reserved organization
namespace, including requests authenticated only by the legacy API key.

Therefore a guessed synthetic owner ID cannot be used to bypass organization
RBAC through the old `/api/v1/companies` API.

## Compatibility

Phase 18C deliberately does not yet introduce organization-wide active-company
selection.

Existing Telegram owner flows, personal company behavior, scoring, monitoring,
tender history and RAG remain on the existing owner-based path.

The next migration step will introduce organization active-company context and
then move scoring/monitoring incrementally.

## Validation

Focused company/organization/auth/API regression:

`55 passed`

Full suite:

`228 passed, 1 skipped, 38 subtests passed`

The remaining warning is the existing Starlette/httpx deprecation warning.

`compileall` passes.

`git diff --check` reports no whitespace errors; Windows may display
LF-to-CRLF working-copy warnings.
