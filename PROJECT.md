# TenderLens AI — v1.0.0 project status

TenderLens AI is a completed portfolio MVP for monitoring and analyzing procurement opportunities. The repository demonstrates the complete path from live source discovery to document analysis, structured scoring, semantic retrieval, persistence, API exposure and containerized deployment.

## Implemented scope

| Area | Status | Implementation |
|---|---|---|
| Project foundation | Complete | Python 3.12 package layout, config, tests, Git hygiene |
| Telegram bot | Complete | aiogram polling, commands, PDF workflow |
| PDF extraction | Complete | PyMuPDF, bounds, timeout worker, clear scan/corruption errors |
| LLM layer | Complete | GigaChat provider abstraction, TLS/proxy support, structured output |
| Structured tender analysis | Complete | strict Pydantic model + JSON validation |
| Company-fit scoring | Complete | deterministic, explainable Python rules |
| Persistence / dedup | Complete | SQLite, SHA-256, owner-scoped history |
| RAG | Complete | page chunks, multilingual FastEmbed, Qdrant local, grounded answers |
| Tender monitoring | Complete | configurable EIS RSS, pre-filter, subscriptions, dedup |
| FastAPI | Complete | health, history, PDF analysis, scoring, RAG, monitoring, Swagger |
| Docker | Complete | non-root image, healthcheck, named persistent volume, localhost bind |
| Portfolio polish | Complete | CI, smoke test, security/deployment/demo documentation, sample PDF |

## Design principles

1. **Human decision remains final.** Fit scoring is compatibility, not a recommendation or win prediction.
2. **Deterministic rules stay outside the LLM.** Scoring can be reproduced and explained.
3. **Provider boundaries are explicit.** Telegram, API, LLM, source adapters and persistence are separated.
4. **Unknown data is not silently converted into a negative score.** Missing fields are tracked as completeness gaps.
5. **Local state is owner-scoped.** Telegram history and RAG retrieval filter by user/document identifiers.
6. **Secrets are runtime configuration.** `.env` and local data are ignored by Git and excluded from Docker build context.
7. **Portfolio claims match implementation.** OCR, multi-replica production storage, full authentication and automatic bid submission are not claimed.

## Verified end-to-end scenarios

- Telegram bot receives a real PDF and extracts text.
- GigaChat returns structured tender facts.
- Deterministic scoring produces an explainable fit score.
- SQLite history and exact-PDF dedup work.
- Semantic RAG answers paraphrased questions and returns source pages.
- EIS RSS live connectivity works with multiple configured feeds.
- Monitoring finds and deduplicates live procurement notices and supports background subscription state.
- FastAPI serves Swagger/OpenAPI and reports component readiness.
- Docker image builds on Windows Docker Desktop / WSL2 and `/health` returns all components ready after the first FastEmbed cache initialization.

## v1.0.0 boundary

The current deployment is intentionally **single-node**: one API process owns local SQLite and Qdrant local-mode files. This is appropriate for a portfolio/demo deployment. Horizontal scaling requires server-backed storage first.

Raw PDF bytes are not retained by the analysis/history flow. RAG chunks are persisted in Qdrant because retrieval requires them. The configured external LLM can receive bounded extracted text; deployments must apply their own data-retention and provider-compliance policies.

## Next production iterations

- PostgreSQL + migrations.
- Qdrant server/Cloud rather than local mode.
- OCR worker for scan-only documents.
- OAuth/JWT or organization identity provider.
- Rate limiting, metrics, tracing and structured audit events.
- Additional procurement source adapters.
- Separate worker/scheduler topology once state is server-backed.
