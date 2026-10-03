# Phase 18F1 - Organization Invitations Backend

Base commit: `383b8d5` - organization PDF and RAG boundary.

Phase 18F1 adds organization invitation infrastructure and API endpoints.

The Dashboard/UI integration is intentionally deferred to Phase 18F2.

## Invitation storage

A new additive SQLite table stores organization invitations.

Each invitation contains:

- organization ID
- normalized email
- target role
- inviter account ID
- expiration timestamp
- accepted timestamp
- revoked timestamp
- creation timestamp
- SHA-256 hash of the invitation token

Raw invitation tokens are never stored in SQLite.

Invitation tokens are generated with high entropy and returned only when an
invitation is created.

## Roles

Invitations may grant:

- admin
- member
- viewer

The owner role cannot be granted through an invitation.

Owner promotion remains an explicit organization-owner operation through the
existing membership management API.

## Invitation creation

Organization owner/admin may create invitations.

The invited email may belong to:

- an existing TenderLens account;
- a user who has not registered yet.

If the account already belongs to the organization, invitation creation is
rejected.

Only one active invitation for the same organization/email may exist at a
time.

Expired invitations are automatically retired so the address may be invited
again.

## Invitation preview

Public token preview endpoint:

- `GET /api/v1/organizations/invitations/{token}`

The preview exposes:

- organization name
- target role
- expiration time
- masked email hint

The complete invitation email and token hash are not exposed.

## Invitation acceptance

Authenticated endpoint:

- `POST /api/v1/organizations/invitations/{token}/accept`

Acceptance requires the signed-in account email to match the invitation email.

The invitation can therefore be created before registration: the user may
register later using the invited email and then accept the same token.

Acceptance and membership creation happen under the same SQLite
`BEGIN IMMEDIATE` transaction.

The invitation becomes consumed exactly once.

Concurrent acceptance of the same token results in:

- exactly one successful acceptance;
- exactly one organization membership row;
- subsequent/replayed acceptance being rejected.

If a matching membership already exists through another authorized path, the
invitation is consumed without changing that existing role.

## Invitation management

Manager endpoints:

- `GET /api/v1/organizations/{organization_id}/invitations`
- `POST /api/v1/organizations/{organization_id}/invitations`
- `DELETE /api/v1/organizations/{organization_id}/invitations/{invitation_id}`

Listing invitations never returns raw invitation tokens.

Revoked or expired invitations cannot be accepted.

## Security

Organization invitation management requires Web session identity.

Legacy API keys are not accepted as organization invitation identity.

Invitation acceptance also requires Web session identity.

State-changing invitation operations use the existing same-origin browser
protection.

Tokens are SHA-256 hashed at rest.

A user signed in with a different email cannot accept another user's
invitation.

## Compatibility

Phase 18F1 is additive.

It does not change:

- existing organization membership semantics;
- existing owner/admin RBAC;
- company workspaces;
- monitoring;
- PDF analysis;
- RAG;
- personal/Telegram workflows.

No email delivery provider is integrated yet.

The create-invitation API returns the one-time token so Phase 18F2 can present
a copyable invitation link in the Dashboard.

## Validation

Invitation-focused suite:

`11 passed`

Phase 18F1 full suite:

`270 passed, 1 skipped, 38 subtests passed`

The remaining warning is the existing Starlette/httpx deprecation warning.

`compileall` passes.

`git diff --check` reports no whitespace errors; Windows may display
LF-to-CRLF working-copy warnings.
