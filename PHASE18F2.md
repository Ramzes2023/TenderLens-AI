# Phase 18F2 - Organization Dashboard Workspace UI

Base checkpoint: Phase 18F1 organization invitation backend.

Phase 18F2 connects the organization model to the authenticated TenderLens
Dashboard while preserving the existing personal v1.5 workspace.

## Organization Dashboard

The Dashboard now provides:

- organization selection;
- shared organization creation;
- organization member display;
- owner/admin membership management;
- role changes;
- member removal;
- invitation creation by email;
- pending invitation listing;
- invitation revocation;
- copyable one-time invitation links.

A dedicated self-membership endpoint allows every organization member to
retrieve their own role without granting manager-only membership-list access.

## Workspace switching

The organization selector is also the workspace selector.

Personal workspace preserves the existing v1.5 account namespace and existing
company/tender/monitoring data.

Shared organizations use organization-scoped APIs for:

- company workspaces;
- active company selection;
- monitoring status;
- on-demand EIS monitoring scans;
- tender history.

No personal data migration is performed by the Dashboard.

Selecting a shared organization does not overwrite or move legacy account data.

## Role-aware UI

Shared organization permissions are reflected in the Dashboard.

Owner, admin and member roles may use writable organization workspace
operations permitted by the backend.

Viewer is read-only for workspace mutations.

Organization membership management remains available only to owner/admin.

Backend authorization remains authoritative; UI restrictions are convenience
controls and are not used as the security boundary.

## Invitation browser flow

A dedicated route is available:

`/invite/{token}`

The invitation page:

- previews the invitation through the public preview API;
- shows organization name, role and masked invited-email hint;
- accepts the invitation through the authenticated session API;
- redirects unauthenticated users to login/register;
- preserves the invitation return path after authentication.

External post-auth redirect targets are rejected.

Invitation token and post-auth return values embedded in inline JavaScript are
escaped against script-breaking HTML sequences.

## Personal compatibility

The existing personal Dashboard behavior remains available.

Personal company creation continues to use:

`POST /api/v1/companies`

with the authenticated account owner namespace.

Existing personal monitoring and tender history endpoints remain in use while
the Personal workspace is selected.

This keeps previously created v1.5 data visible after Phase 18F2.

## Testing

Focused organization/dashboard suite:

`59 passed`

Dashboard regression:

`12 passed`

Full Phase 18F2 suite:

`276 passed, 1 skipped, 38 subtests passed`

One existing Starlette/httpx deprecation warning remains.

`compileall` passes.

`git diff --check` reports no whitespace errors; Git may display normal Windows
LF-to-CRLF working-copy warnings.

JavaScript syntax checking with Node.js was skipped because Node.js is not
installed in the local development environment.

## Scope

Phase 18F2 does not:

- deploy to production;
- change the v1.5.0 release tag;
- migrate production data;
- add billing;
- add email delivery infrastructure;
- enable background organization notifications.

Release-candidate preparation remains a separate next step.
