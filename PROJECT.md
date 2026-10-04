# VALYQON AI - v1.6.0 project status

Phase 20 branding is prepared for review; the application version remains 1.6.0.
This branch does not deploy or relabel the historical v1.6.0 release.

VALYQON AI v1.6.0 extends the authenticated single-node platform with shared organization workspaces, explicit membership roles and invitation-based team onboarding. The repository now demonstrates the path from Web account onboarding and Telegram identity linking through organization-scoped procurement discovery, document analysis, structured scoring, semantic retrieval, persistence, API exposure and containerized deployment.

## Implemented scope

| Area | Status | Implementation |
|---|---|---|
| Project foundation | Complete | Python 3.12 package layout, config, tests, Git hygiene |
| Telegram bot | Complete | aiogram polling, commands, PDF workflow |
| PDF extraction | Complete | PyMuPDF, bounds, timeout worker, clear scan/corruption errors |
| LLM layer | Complete | GigaChat provider abstraction, TLS/proxy support, structured output |
| Structured tender analysis | Complete | strict Pydantic model + JSON validation |
| Company-fit scoring | Complete | deterministic, explainable Python rules |
| Persistence / dedup | Complete | SQLite, SHA-256, personal and organization-isolated history |
| RAG | Complete | page chunks, multilingual FastEmbed, Qdrant local, personal/organization retrieval isolation |
| Tender monitoring | Complete | configurable EIS RSS, personal subscriptions plus organization-scoped on-demand monitoring |
| FastAPI | Complete | health, auth, organizations, memberships, invitations, companies, history, PDF analysis, scoring, RAG, monitoring, Swagger |
| Web accounts | Complete | email/password registration/login/logout, HttpOnly sessions, owner isolation |
| Web Dashboard | Complete | authenticated personal/shared workspace selector, organization management, invitations, EIS scan and Telegram connection UX |
| Web ↔ Telegram identity | Complete | one-time hashed deep-link tickets, atomic redemption, guarded owner migration |
| Auth hardening | Complete | browser same-origin provenance checks, bounded login throttling, expired-session cleanup |
| Organizations / RBAC | Complete | personal/shared organizations, owner/admin/member/viewer membership enforcement |
| Organization workspaces | Complete | shared companies, shared active company, scoring, monitoring, tender history, PDF and RAG boundaries |
| Invitations | Complete | email-bound SHA-256-at-rest one-time invitations with expiration, revocation and atomic acceptance |
| Docker | Complete | non-root image, healthcheck, named persistent volume, localhost bind |
| Portfolio polish | Complete | CI, smoke test, security/deployment/demo documentation, sample PDF |

## Design principles

1. **Human decision remains final.** Fit scoring is compatibility, not a recommendation or win prediction.
2. **Deterministic rules stay outside the LLM.** Scoring can be reproduced and explained.
3. **Provider boundaries are explicit.** Telegram, API, LLM, source adapters and persistence are separated.
4. **Unknown data is not silently converted into a negative score.** Missing fields are tracked as completeness gaps.
5. **Tenancy is explicit.** Personal/Telegram compatibility remains owner-scoped, while shared organization resources require membership and are isolated by organization namespace.
6. **Secrets are runtime configuration.** `.env` and local data are ignored by Git and excluded from Docker build context.
7. **Portfolio claims match implementation.** OCR, multi-replica public production readiness and automatic bid submission are not claimed.

## Verified end-to-end scenarios

- Telegram bot receives a real PDF and extracts text.
- GigaChat returns structured tender facts.
- Deterministic scoring produces an explainable fit score.
- SQLite history and exact-PDF dedup work.
- Semantic RAG answers paraphrased questions and returns source pages.
- EIS RSS live connectivity works with multiple configured feeds.
- Monitoring finds and deduplicates live procurement notices and supports background subscription state.
- FastAPI serves Swagger/OpenAPI and reports component readiness.
- A Web user can register/login, create a company and run real owner-scoped EIS monitoring without entering an API key or owner ID.
- Web → Telegram linking has passed a real end-to-end flow: the owner namespace migrates to the verified Telegram user ID while the Web session remains valid.
- Telegram linking concurrency tests allow exactly one claim of a one-time ticket.
- Shared organizations isolate companies, active-company state, scoring, monitoring, tender history, PDF deduplication and RAG namespaces.
- Organization invitation acceptance is email-bound, one-time and concurrency-tested; replay is rejected.
- Dashboard users can switch between the personal compatibility workspace and shared organization workspaces with role-aware controls.
- Docker image builds on Windows Docker Desktop / WSL2 and `/health` returns all components ready after the first FastEmbed cache initialization.

## v1.6.0 boundary

The current deployment remains intentionally **single-node and localhost-first**. Shared organization tenancy and role enforcement are implemented for the application, but this is not yet a horizontally scaled public SaaS topology. One API process owns local SQLite and Qdrant local-mode files. Public or multi-replica operation still requires server-backed storage, structured audit events, HTTPS/reverse-proxy hardening and shared/distributed security controls.

## Next production iterations

- PostgreSQL + migrations.
- Qdrant server/Cloud rather than local mode.
- OCR worker for scan-only documents.
- Structured organization audit events and administrative observability.
- Public domain/HTTPS/reverse-proxy deployment with edge/distributed rate limiting.
- Metrics and tracing.
- Additional procurement source adapters.
- Separate worker/scheduler topology once state is server-backed.

## Phase 13 — multi-company commercialization foundation

VALYQON AI now supports multiple persistent company workspaces per owner, active-company switching, per-company EIS keyword searches, company-scoped monitoring deduplication, and active-profile scoring through Telegram and FastAPI. This is the foundation for onboarding different industries without editing server configuration per customer.

## Phase 17 — Web accounts + authentication

Phase 17 turns the Web Dashboard into a real account surface: register/login/logout, HttpOnly sessions, owner isolation, Web company creation, and safe Web-to-Telegram identity linking. The linking flow stores only SHA-256 ticket digests, uses a 10-minute one-time lifetime, atomically claims redemption, guards owner migration, and preserves the account session across the owner-ID change.

Security hardening adds explicit browser cross-site provenance rejection for state-changing requests, a bounded in-process login limiter, and expired-session cleanup. The legacy API-key path remains for supported personal/integration compatibility.

## Phase 18 - organizations, RBAC and shared workspaces

Phase 18 adds persistent organizations and memberships with owner/admin/member/viewer roles, transactional authorization checks, shared company workspaces and active-company state, organization-scoped scoring and monitoring, isolated tender/PDF/RAG namespaces, invitation-based team onboarding and Dashboard workspace switching. The legacy API key is deliberately not organization identity.

The release still stops short of public multi-replica SaaS hosting: PostgreSQL/migration tooling, Qdrant server/Cloud, structured audit events, distributed throttling and public HTTPS deployment remain separate production work.
