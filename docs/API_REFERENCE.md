# API orientation

See the running OpenAPI schema at `/docs` for complete request and response contracts.


| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Service/component readiness |
| POST | `/api/v1/auth/register` | Create Web account and session |
| POST | `/api/v1/auth/login` | Authenticate and create session |
| POST | `/api/v1/auth/logout` | Invalidate current session |
| GET | `/api/v1/auth/me` | Current authenticated account |
| POST | `/api/v1/auth/telegram-link` | Create a short-lived Telegram deep-link ticket |
| GET | `/api/v1/companies` | Personal/legacy owner-scoped company profiles |
| POST | `/api/v1/companies` | Create personal company profile |
| POST | `/api/v1/companies/{id}/activate` | Switch personal active company |
| GET | `/api/v1/organizations` | Organizations visible to the current Web account |
| POST | `/api/v1/organizations` | Create a shared organization |
| GET | `/api/v1/organizations/{id}/members` | Owner/admin membership management view |
| POST | `/api/v1/organizations/{id}/invitations` | Create an organization invitation |
| GET | `/api/v1/organizations/{id}/companies` | Shared organization company workspaces |
| POST | `/api/v1/organizations/{id}/companies` | Create a shared organization company |
| GET | `/api/v1/organizations/{id}/tenders` | Organization-scoped tender history |
| POST | `/api/v1/organizations/{id}/analysis/pdf` | Organization-scoped PDF analysis |
| POST | `/api/v1/organizations/{id}/rag/ask` | Organization-scoped semantic RAG |
| GET | `/api/v1/tenders` | Personal/legacy owner-scoped tender history |
| GET | `/api/v1/tenders/{id}` | Tender detail |
| POST | `/api/v1/analysis/pdf` | PDF analysis pipeline |
| POST | `/api/v1/scoring/evaluate` | Deterministic fit score |
| POST | `/api/v1/rag/ask` | Grounded question answering |
| GET | `/api/v1/monitoring/status` | Monitoring status |
| POST | `/api/v1/monitoring/scan` | Manual source scan |

Browser Web flows use the HttpOnly `tenderlens_session` cookie. Session-authenticated personal endpoints resolve the owner from the account instead of trusting a browser-supplied owner ID. Organization endpoints use account membership plus role checks and do not accept the legacy API key as organization identity. The legacy `X-API-Key` path remains available only for supported personal/integration compatibility when `TENDERLENS_API_KEY` is configured. `/health` and OpenAPI remain accessible for local readiness/documentation.
