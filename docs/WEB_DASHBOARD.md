# Web Dashboard

The TenderLens Dashboard is the authenticated browser workspace for personal
and shared organization procurement workflows.

## URL

When the API is running locally:

`http://127.0.0.1:8000/dashboard`

Unauthenticated users are redirected to `/login`.

## Personal workspace

The Personal workspace preserves the existing v1.5-compatible account data:

- company workspaces;
- active-company switching;
- monitoring status;
- on-demand EIS scan;
- recent analyzed tender history;
- Telegram linking.

The browser does not ask the user to enter an API key or owner ID.

## Shared organization workspace

Users can create or select shared organizations.

The selected shared organization controls:

- shared company workspaces;
- shared active company;
- organization-scoped monitoring status;
- on-demand organization EIS scans;
- organization tender history.

The backend also exposes organization-scoped scoring, PDF analysis and RAG.

## Roles

Organization roles are `owner`, `admin`, `member` and `viewer`.

Owner/admin can manage supported memberships and invitations.
Owner/admin/member can perform supported writable workspace operations.
Viewer is read-only for organization mutations.

Dashboard controls reflect those permissions, but backend authorization remains
the security boundary.

## Invitations

Owner/admin can create email-bound organization invitations and copy the
one-time `/invite/{token}` link.

The invitation browser page supports public preview plus authenticated
acceptance. Login/register preserve a safe local invitation return path.

Raw invitation tokens are returned only at creation and are not stored in
plaintext in SQLite.

## Authentication and security

Browser requests use the HttpOnly Web session cookie.

State-changing session requests apply the same-origin/provenance protections
used by the API.

Organization APIs require session identity plus membership/role authorization.
The legacy `X-API-Key` path is not organization identity.

TenderLens v1.6.0 remains localhost-first. Public deployment still requires
HTTPS/reverse-proxy hardening, distributed throttling, server-backed storage,
retention/backups and structured audit logging.
