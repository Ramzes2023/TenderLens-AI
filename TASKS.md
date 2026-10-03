## v1.6.0 release candidate preparation

- [x] Phase 18A-F2 organization/RBAC feature work completed on the development branch.
- [x] Source version and Compose target advanced from 1.5.0 to 1.6.0 without moving the existing v1.5.0 tag.
- [x] Release-facing README, architecture, security, project and Dashboard documentation updated for Phase 18.
- [x] Full v1.6.0 regression after invitation referrer hardening: 279 passed, 1 skipped, 38 subtests passed.
- [x] Built isolated `tenderlens-ai:1.6.0-rc1`, verified embedded version 1.6.0, Docker health and component readiness.
- [x] Passed isolated Docker session/organization/invitation/security smoke, including one-time acceptance, replay protection, SHA-256-at-rest token verification and no-referrer invitation/auth pages.
- [x] Passed additive Phase 18 migration against a consistent snapshot of the current v1.5.0 production SQLite database: integrity OK, foreign-key check clean and all original v1.5.0 rows preserved.
- [x] Verified existing Web account/session/Telegram link, AluTrade, active company, 40 monitoring dedup rows and monitoring subscription survive the v1.5.0 -> v1.6.0 migration; AluTrade is backfilled to the personal organization.
- [ ] Push release-prep commit and open the Phase 18 pull request.
- [ ] Require CI to pass before merge.
- [ ] Create the v1.6.0 tag/GitHub Release only after explicit release approval.
- [ ] Production deployment remains a separate explicit step.

## v1.5.0 released and deployed

- [x] Added email/password Web account registration, login and logout.
- [x] Added scrypt password hashing and high-entropy session tokens stored as SHA-256 digests.
- [x] Added HttpOnly/SameSite Web session cookies and session-based owner isolation.
- [x] Removed the Dashboard requirement to manually enter API key / owner ID.
- [x] Added Web company creation and no-company guards.
- [x] Verified real Web account → company → EIS monitoring flow.
- [x] Added guarded Web-owner → Telegram-owner migration while preserving supported SQLite state.
- [x] Added one-time 10-minute Telegram link tickets with SHA-256-at-rest, invalidation and reuse protection.
- [x] Added atomic/concurrent Telegram ticket claim and safe claim release on failed migration.
- [x] Integrated `/start link_<token>` and `/link <token>` into the aiogram runtime without breaking normal `/start`.
- [x] Verified real Web → Telegram → Web end-to-end linking and session continuity.
- [x] Added Dashboard `Connect Telegram` UX with bounded polling, popup fallback and connected-state refresh.
- [x] Added browser cross-origin provenance protection for state-changing session requests.
- [x] Added bounded login brute-force throttling and expired-session cleanup.
- [x] Phase 17 regression: 196 passed, 1 skipped, 38 subtests passed before documentation/version bump.
- [x] Release version bumped to 1.5.0.
- [x] Re-ran full tests and compile checks after documentation/version bump: 196 passed, 1 skipped, 38 subtests passed.
- [x] Built isolated `tenderlens-ai:1.5.0-rc1` Docker image and verified embedded version 1.5.0.
- [x] Passed isolated Docker integration: health, register, session `/me`, company creation, Telegram-link ticket and cross-origin 403 protection.
- [x] Passed migration test against a consistent COPY of the existing production SQLite DB: AluTrade, active-company and monitoring state preserved; Web session survived owner migration; DB integrity remained OK.
- [x] GitHub branch pushed; PR #5 passed all checks and was merged into `main`.
- [x] Tagged `v1.5.0` and published the GitHub Release.
- [x] Created and verified a pre-v1.5.0 production DB backup, deployed API and bot on `tenderlens-ai:1.5.0`, preserved the Docker volume, and verified production health/data integrity.

## v1.4.0 completed

- Added browser-based Web Dashboard at /dashboard.
- Added system health and component status view.
- Added company workspace list and active-company switching.
- Added monitoring status for the active company profile.
- Added recent analyzed tender history view.
- Added on-demand EIS scan with prices, matching reasons, and zakupki.gov.ru links.
- Reused the existing protected FastAPI endpoints and X-API-Key authentication.
- Added Web Dashboard documentation and automated tests.
- Release version bumped to 1.4.0.

# TenderLens AI — implementation checklist

## v1.3.0 completed
- Added guided company profile editing.
- Added safe company deletion with explicit confirmation.
- Added easier company switching from Telegram.
- Improved multi-company management UX.
- Added company management documentation and tests.
- Release version bumped to 1.3.0.

## v1.2.0 completed
- Guided Telegram company onboarding via /company_setup.
- Step-by-step company profile creation with confirmation.
- Added /company_cancel support.
- Preserved /company_add for advanced users.
- Added automated onboarding tests.
- Release version bumped to 1.2.0.

## v1.1.0 completed

- [x] Phase 1 — project foundation, package structure and configuration.
- [x] Phase 2 — Telegram bot startup and basic commands.
- [x] Phase 3 — bounded PDF upload and local text extraction.
- [x] Phase 4 — GigaChat provider abstraction and live health check.
- [x] Phase 4.1 — portable explicit proxy configuration.
- [x] Phase 5 — strict structured tender analysis.
- [x] Phase 6 — deterministic company-profile scoring.
- [x] Phase 7 — SQLite history and owner-scoped SHA-256 deduplication.
- [x] Phase 8 — document Q&A RAG flow.
- [x] Phase 8.1 — multilingual semantic embeddings + Qdrant local mode.
- [x] Phase 9 — EIS RSS monitoring, pre-filter, subscriptions and deduplication.
- [x] Phase 10 — FastAPI backend and Swagger/OpenAPI.
- [x] Phase 11 — Docker image, Compose, persistent volume and healthcheck.
- [x] Phase 12 — portfolio README, architecture/security/deployment/demo docs, CI, smoke test and synthetic demo PDF.

## Verified quality gates

- [x] Offline automated test suite passes on the Windows development environment.
- [x] FastAPI `/health` works locally and in Docker.
- [x] Docker service reports `healthy`.
- [x] FastEmbed semantic model works on host and inside Docker.
- [x] `.env` and `data/` are excluded from Git/Docker context.
- [x] API binds to localhost by default.
- [x] Container runs as a non-root user.
- [x] Portfolio docs distinguish implemented behavior from limitations.

## Deliberate post-v1 backlog

- [ ] OCR for scan-only PDFs.
- [ ] PostgreSQL + schema migration tooling.
- [ ] Qdrant server/Cloud for multi-process deployment.
- [ ] Distributed/edge rate limiting, structured audit events and server-backed tenancy infrastructure for public multi-tenant deployment.
- [ ] Metrics/tracing/centralized logs.
- [ ] Additional source adapters: B2B-Center, РТС-тендер, Сбербанк-АСТ, Росатом.
- [ ] Optional second LLM provider.
- [ ] Automated retention policies for RAG/database data.
- [ ] Deployment to a public HTTPS environment after security hardening.

## Phase 13 — Multi-company core

- [x] Persistent company workspaces in SQLite.
- [x] Active company per owner.
- [x] Telegram company create/list/show/switch commands.
- [x] Per-company EIS RSS searches generated from profile keywords.
- [x] Per-company monitoring deduplication scope.
- [x] Active-company deterministic scoring for PDF analysis.
- [x] Company CRUD subset in protected FastAPI.
- [x] Web authentication and account/session owner isolation (Phase 17).
- [x] Organization memberships and roles/permissions (Phase 18).
- [ ] Supplier-intelligence sources for `buy` mode.
- [ ] International tender source adapters.


## Phase 18 - Multi-Tenant Security + Organizations + Roles (feature-complete; release preparation)

### Phase 18A — Organization/membership foundation
- [x] Additive SQLite organizations and organization_members, role enum/CHECK, FK/indexes.
- [x] Atomic registration + personal organization + owner membership.
- [x] Idempotent startup/backfill; unique personal_account_id prevents duplicates.
- [x] Nullable company organization_id; only unambiguous authenticated owner mappings.
- [x] Internal repository/service, explicit allowed-role authorization primitives.
- [x] Last-owner preservation and concurrency tests on temporary SQLite databases.
- [x] Legacy Telegram owners and v1.5.0 HTTP/session/API-key behavior remain compatible.
- [ ] Later Phase 18: organization-scoped enforcement across endpoints/resources.
- [x] Phase 18B: session-only Organization HTTP API.
- [x] Phase 18B: transactional owner/admin RBAC for membership management.
- [x] Phase 18B: legacy API key is not accepted as organization identity.
- [x] Phase 18B: same-origin protection and cross-organization access tests.
- [x] Phase 18C: organization-scoped shared company workspaces.
- [x] Phase 18C: owner/admin/member/viewer company RBAC.
- [x] Phase 18C: transactional company authorization and mutation.
- [x] Phase 18C: reserved organization owner namespace isolated from legacy owner APIs.
- [x] Phase 18C: legacy API-key path cannot expose shared organization companies.
- [x] Phase 18D1: shared active company per organization.
- [x] Phase 18D1: organization-wide active selection visible to all members.
- [x] Phase 18D1: owner/admin/member activation; viewer read-only.
- [x] Phase 18D1: cross-organization activation isolation and concurrency coverage.
- [x] Phase 18D1: active-company replacement after deletion.
- [x] Phase 18D2: organization-scoped deterministic scoring using the shared active company.
- [x] Phase 18D2: organization-scoped on-demand EIS monitoring using the shared active company.
- [x] Phase 18D2: organization/company-specific monitoring dedup namespace.
- [x] Phase 18D2: transactional membership re-check before monitoring dedup persistence.
- [x] Phase 18D2: organization monitoring state isolated from legacy owner/Telegram monitoring.
- [x] Phase 18D2: session-only workflow identity and same-origin write protection.
- [x] Phase 18E1: shared organization tender-history namespace in SQLite.
- [x] Phase 18E1: organization tender read/write RBAC.
- [x] Phase 18E1: reserved organization owner namespace centralized and blocked from legacy owner APIs.
- [x] Phase 18E1: organization tender IDs and PDF hashes isolated across organizations.
- [x] Phase 18E1: organization history separated from legacy personal/Telegram tender history.
- [x] Phase 18E2: organization-scoped PDF upload and analysis.
- [x] Phase 18E2: organization PDF duplicate detection isolated by organization namespace.
- [x] Phase 18E2: shared active-company scoring for organization PDF analysis.
- [x] Phase 18E2: organization semantic RAG using the reserved synthetic owner namespace.
- [x] Phase 18E2: legacy, organization A and organization B RAG namespaces isolated for the same PDF hash.
- [x] Phase 18E2: membership re-checks around long-running PDF/RAG workflows.
- [x] Phase 18E2: organization PDF/RAG endpoints remain session-only and cross-origin protected.
- [x] Phase 18F1: organization invitation persistence and one-time token flow.
- [x] Phase 18F1: invitation tokens SHA-256 hashed at rest.
- [x] Phase 18F1: invite existing or not-yet-registered users by email.
- [x] Phase 18F1: owner/admin invitation management with admin/member/viewer target roles.
- [x] Phase 18F1: atomic invitation acceptance and replay/concurrency protection.
- [x] Phase 18F1: email-bound acceptance, revocation and expiration handling.
- [x] Phase 18F1: session-only and same-origin protected invitation mutations.
- [x] Phase 18F2: organization Dashboard selector and workspace UI.
- [x] Phase 18F2: preserve personal v1.5 workspace and existing account data.
- [x] Phase 18F2: shared organization companies and active-company switching.
- [x] Phase 18F2: organization monitoring status and on-demand scan UI.
- [x] Phase 18F2: organization tender-history UI.
- [x] Phase 18F2: role-aware owner/admin/member/viewer Dashboard controls.
- [x] Phase 18F2: member role management and removal UI.
- [x] Phase 18F2: invitation creation, listing, revocation and copy-link UX.
- [x] Phase 18F2: browser invitation preview/accept flow with safe auth return.
- [x] Phase 18 release-candidate preparation started with the v1.6.0 source/documentation bump.
- [ ] Later: background organization notifications.

Not full multi-tenant security: existing endpoints still authorize owner_user_id.
No billing, background organization notifications, public HTTPS deployment or production migration performed.
See PHASE18A.md for migration and security boundaries.
