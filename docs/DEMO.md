# VALYQON AI — 5–10 minute demo

A prepared portfolio walkthrough, not a claim of a hosted public SaaS.
Use synthetic documents and separate demo accounts; never demonstrate with customer secrets.

## Prepare before the timer starts

- Follow the [fresh-checkout quick start](../README.md#quick-start). Start the API service first.
- Check `/health`. Configure GigaChat credentials and quota, the trusted CA bundle,
  and the embedding model cache using the [deployment guide](DEPLOYMENT.md).
  Downloading models is not part of the timed demo.
- Prepare `examples/sample_tender.pdf`, a company profile, and two demo accounts.
- Configure a working EIS feed if demonstrating live discovery. An empty feed is a valid result.
- Run the test suite beforehand and show its real output or the latest CI run.
- If using Telegram, start only one polling process per token. Do not start a local
  bot while its Docker counterpart is running. API and bot have separate local RAG indexes.

## Minutes 0–1: identity and personal workspace

Open `/dashboard`, register or sign in, and show the Personal workspace.
Explain that the session identifies the account: the browser does not ask for an
API key or an arbitrary owner ID. Personal company/history data stays separate
from shared organization data.

## Minutes 1–3: a team workspace

Create/select a shared organization and add a synthetic company profile.
As owner/admin, create an invitation for the second account's email with viewer role.
Open that invitation in a separate browser profile, sign in as that account and accept.

Show the viewer's read-only controls. Explain that backend membership/role checks,
not hidden buttons, enforce permissions. Invitations are email-bound, expire,
can be revoked and are accepted atomically; this is not a claim of email verification.
Do not show or publish live invitation URLs in a recorded demo.

## Minutes 3–5: facts and an explainable score

In the owner browser session, open `/docs` on the same origin as the Dashboard.
Use the current OpenAPI request schema for:

- `POST /api/v1/organizations/{id}/analysis/pdf`
- the selected organization's company/profile context.

Upload `examples/sample_tender.pdf` using the organization ID returned by the API
or selected in the Dashboard. Inspect the extracted facts and deterministic score
separately. Submit the same file in the same context to demonstrate deduplication.

The Dashboard provides workspace/history operations; this step demonstrates the
backend analysis API, not a Dashboard PDF-upload screen. Organization APIs require
an authenticated session, not the legacy API key.

Alternative: send the PDF to the configured Telegram bot to demonstrate the personal
workflow. Telegram linking does not turn that workflow into a shared organization.

## Minutes 5–7: grounded questions

Through the same API transport and organization context, use
`POST /api/v1/organizations/{id}/rag/ask`. Supply the document identifier and fields
required by the current OpenAPI schema. Ask a question such as:

> Что произойдет, если поставщик задержит доставку?

Compare the answer and cited pages with the actual PDF. Missing evidence should
be acknowledged, not presented as fact. The question is useful even if the document
contains no answer.

For the Telegram alternative, use `/ask` after uploading the PDF through that bot.
Do not assume that an API-indexed document is also indexed by the bot.

## Minutes 7–9: discovery and permissions

Run an on-demand scan in the selected Dashboard workspace. Show actual results,
including an empty result or a source error if that is what happened. EIS RSS is a
discovery/pre-filter layer, not full tender-document analysis.

Compare the viewer workspace again: permitted reads remain available, mutations
are denied by the backend. Explain that organization monitoring is on-demand;
background organization notifications remain future work.

## Minute 10: explain the trade-offs

- LLM extraction, deterministic scoring and human decisions have separate roles.
- Retrieval is scoped by personal/organization namespace and document hash.
- SQLite and Qdrant local keep the MVP inspectable but constrain multi-process scale.
- Live model requests consume provider quota; mocks make tests independent of it.

Close with [security limits](../SECURITY.md), [architecture](../ARCHITECTURE.md)
and [interview notes](PORTFOLIO.md). Public hosting, HTTPS hardening, server-backed
storage and operational controls are next steps, not current production claims.
