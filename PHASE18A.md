# Phase 18A — design and audit

Base: main/origin/main 2a77bd4, v1.5.0. Development branch phase18-organizations-rbac.
No production startup/migration, deployment, tag or package version change.

## Current architecture audit
- auth_accounts owns unique owner_user_id; auth_sessions and auth_telegram_links reference account ID.
- app.auth repository/service owns registration, sessions and safe Telegram owner migration.
- app.api.security resolves the session account and rejects another requested owner;
  legacy X-API-Key remains supported. app.bot.linking uses Telegram from_user.id.
- company_workspaces/company_active, monitor_subscriptions/monitor_seen, tenders and
  local rag_chunks use owner_user_id. Qdrant ownership is outside SQLite; existing
  PDF-history migration restriction remains. No change to those authorization paths.
- owner references also appear in api routes/schemas/dashboard, bot documents/history/
  monitoring, company service, database repository, rag service/stores and monitoring service.
- API/bot initialize repositories on one SQLite path; initialization uses CREATE IF NOT EXISTS.
  There is no external migration framework. Tests cover auth, legacy API keys, company
  isolation, owner migration, link concurrency and Dashboard.

## Additive schema
organizations: id, name, timestamps, created_by_account_id FK, personal_account_id
nullable UNIQUE FK. Separate personal key distinguishes a default from additional
organizations created by the same account. organization_members: composite PK
(organization_id,account_id), role CHECK owner/admin/member/viewer, timestamp, FKs.
Account index supports scoped listing. Account deletion is RESTRICT while referenced.
company_workspaces gains nullable organization_id FK with an index. Company API/model
shape is deliberately unchanged in 18A; owner remains the authorization source.

## Migration and transactions
Auth and company initialization invoke connection-level migrate under BEGIN IMMEDIATE.
DDL and backfill are in one transaction (no executescript inside migration).
The code handles either initialization order. No auth accounts means no invented users.
All existing Web accounts receive exactly one personal org and owner membership.
Registration adds them within the existing account transaction. Company mapping uses
unique auth owner -> personal organization + membership; NULL only is filled, existing
organization assignments are never overwritten. IDs and owner values are preserved.
Company creation and successful Telegram owner linking fill only the affected owner's unassigned mappings; full-table company backfill is reserved for startup migration.
Legacy-only companies stay NULL until a real Web account links through existing behavior.

## Internal API and security boundaries
Repository methods are trusted persistence operations, NOT public HTTP endpoints.
Service scoped reads require active account + membership; explicit allowed-role sets
are used (empty set denies access), never an implicit numeric role ranking.
Internal membership mutation methods require future caller-side actor authorization;
18A does not expose them over HTTP. All repository mutations preserve a last owner,
with BEGIN IMMEDIATE serializing competing changes. A personal organization's original
account cannot be demoted/removed; ownership transfer is available for non-personal orgs.
Repeated backfill does not reset existing roles. No raw SQL permission guarantee is
claimed: code with arbitrary database write access can bypass application invariants.
No invitations, billing, membership HTTP/UI or global RBAC enforcement yet.

## Review before future deployment
Backfill holds a SQLite write lock; assess production volume and backup before rollout.
Each registered account gets its own personal org even if it joins shared orgs later.
No users/data were copied from production for tests; all new tests use temporary files.
Nullable company organization_id is a compatibility bridge, not security enforcement.
