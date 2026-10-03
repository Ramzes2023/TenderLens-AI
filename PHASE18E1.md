# Phase 18E1 - Organization Tender Data Boundary

Base commit: `1b25c46` - organization scoring and monitoring context.

Phase 18E1 introduces organization-scoped SQLite tender history and closes
legacy owner-ID access to the reserved organization namespace.

PDF upload and Qdrant/RAG organization integration are intentionally deferred
to Phase 18E2.

## Shared tenancy namespace

The reserved organization compatibility namespace is centralized in:

`app/tenancy.py`

Organization storage owner IDs use:

`8_000_000_000_000 + organization_id`

The helper is shared by companies, monitoring and tender history.

Synthetic organization owner IDs are internal storage identifiers only.
They are never authentication identities.

## Legacy namespace protection

Legacy owner-based HTTP endpoints now reject reserved organization owner IDs.

A legacy API key cannot guess a synthetic organization owner ID and use older
owner-scoped endpoints to access organization resources.

Reserved organization owner requests return HTTP 403.

Existing normal legacy owner behavior remains unchanged.

## Organization tender persistence

TenderRepository now supports explicit organization-scoped operations:

- find by hash
- find by ID
- list recent
- save successful analysis

Organization tender rows remain physically compatible with the existing
`tenders` table while being isolated under the reserved organization owner
namespace.

The existing database schema and production rows do not require destructive
migration.

## RBAC

Organization tender history may be read by:

- owner
- admin
- member
- viewer

Organization tender persistence is allowed to:

- owner
- admin
- member

Viewer is read-only.

Writes perform membership/role authorization in the same SQLite
`BEGIN IMMEDIATE` transaction as persistence.

## HTTP API

New session-authenticated endpoints:

- `GET /api/v1/organizations/{organization_id}/tenders`
- `GET /api/v1/organizations/{organization_id}/tenders/{tender_id}`

Organization tender detail intentionally does not expose the synthetic
`owner_user_id`.

API-key-only access is not accepted as organization identity.

## Isolation guarantees

Tender IDs from another organization are not visible through the current
organization endpoint.

The same PDF SHA-256 can exist independently in different organizations.

Organization tender history remains separate from existing personal/Telegram
owner history.

Revoked members lose organization tender access.

## Compatibility

Phase 18E1 does NOT yet add:

- organization PDF upload/analysis
- organization RAG indexing
- organization RAG questions
- Qdrant organization namespace migration
- background organization notifications

Legacy tender history and existing Telegram data remain unchanged.

## Validation

Focused organization/data regressions pass.

Full suite after Phase 18E1:

`249 passed, 1 skipped, 38 subtests passed`

The full suite passed twice.

The remaining warning is the existing Starlette/httpx deprecation warning.

`compileall` passes.

`git diff --check` reports no whitespace errors; Windows may display
LF-to-CRLF working-copy warnings.
