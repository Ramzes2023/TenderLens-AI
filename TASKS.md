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
- [ ] Proper user authentication/authorization and rate limiting.
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
- [ ] Web authentication and organization memberships.
- [ ] Supplier-intelligence sources for `buy` mode.
- [ ] International tender source adapters.
