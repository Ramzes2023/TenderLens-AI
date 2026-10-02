# Web Dashboard (Phase 16)

Phase 16 adds a lightweight operator dashboard to the existing FastAPI service.

## URL

When the API is running locally, open:

`http://127.0.0.1:8000/dashboard`

## What the dashboard shows

- API version and component health
- company workspaces and the active company
- one-click company activation
- monitoring status and feed mode
- recent PDF tender-analysis history
- an on-demand company-aware EIS scan with links to procurement notices

## Authentication model

This is a local/single-node MVP dashboard, not a public SaaS authentication system.

Protected API calls still use the existing `X-API-Key` mechanism. The operator enters the API key and owner / Telegram user ID in the page. The browser stores them in `sessionStorage`, so they are not embedded in the HTML and are cleared when the browser session is cleared.

Do not expose `/dashboard` directly to the public internet without adding a production authentication/session layer, HTTPS, CSRF protections where applicable, rate limiting, and tenant authorization.

## Existing API reuse

The dashboard deliberately reuses existing endpoints instead of introducing a second business-logic layer:

- `GET /health`
- `GET /api/v1/companies`
- `POST /api/v1/companies/{id}/activate`
- `GET /api/v1/tenders`
- `GET /api/v1/monitoring/status`
- `POST /api/v1/monitoring/scan`

Telegram workflows and the REST API continue to operate independently.
