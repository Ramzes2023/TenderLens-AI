# Phase 18D1 - Shared Organization Active Company Context

Base commit: `0765fe8` - Phase 18C encoding cleanup.

Phase 18D1 introduces one shared active company per organization.

This checkpoint deliberately does not yet migrate scoring or monitoring.
It establishes and validates the shared active-company state first.

## Active company behavior

Organization company responses now expose:

- `is_active`

New session-authenticated endpoints:

- `GET /api/v1/organizations/{organization_id}/companies/active`
- `POST /api/v1/organizations/{organization_id}/companies/{company_id}/activate`

The first company created inside an organization automatically becomes active.

Creating additional companies does not unexpectedly replace the organization's
current active company.

## Shared context

The active company belongs to the organization rather than an individual user.

If one authorized member switches the active company, other members of the same
organization immediately observe the same active company.

The existing `company_active` table is reused with the reserved organization
compatibility owner namespace:

`8_000_000_000_000 + organization_id`

This synthetic owner ID remains internal compatibility state and is not an
authorization identity.

## RBAC

Reading the active company requires organization membership.

Activation is allowed to:

- owner
- admin
- member

Viewer remains read-only and cannot switch the active company.

Authorization and active-company mutation happen inside the same SQLite
`BEGIN IMMEDIATE` transaction.

## Isolation

A company belonging to another organization cannot be activated even if its
numeric company ID is known.

Legacy owner-based company APIs remain isolated from the reserved organization
namespace.

## Deletion behavior

When the currently active shared company is deleted:

- another remaining organization company is selected as active;
- if no companies remain, the organization active-company state is removed.

## Concurrency

Concurrent activation attempts are serialized by SQLite write locking.

After concurrent activation:

- the database remains valid;
- exactly one organization company is active;
- the active company is one of the successfully requested companies.

## Compatibility

Legacy personal/Telegram active-company behavior is unchanged.

This phase does NOT yet move:

- scoring
- EIS monitoring
- tender history
- PDF ownership
- RAG

to organization active-company context.

## Validation

Focused organization/company/API regression:

`52 passed`

Full suite:

`233 passed, 1 skipped, 38 subtests passed`

The remaining warning is the existing Starlette/httpx deprecation warning.

`compileall` passes.

`git diff --check` reports no whitespace errors; Windows may display
LF-to-CRLF working-copy warnings.
