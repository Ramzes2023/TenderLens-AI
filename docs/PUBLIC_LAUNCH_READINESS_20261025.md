# VALYQON AI — public go-live readiness, 25 October 2026

This document is a release blocker report, **not** a declaration of public deployment.

## Current source of truth
- PR #264 was merged into main. Keep the user-approved premium website and account workbench.
- Subsequent fix/audit PR #280 and notification journal PR #281 have green automated checks, but their source branches diverge from main's squash history; **do not directly merge a conflicting retarget**. Main already contains several of their fixes. The exact production artifact must be built from a fully reviewed main-based release candidate.
- This release-candidate branch is based on current main and changes public analytics mode from `demo` to `real`. If connector data is absent, no fictitious procurement statistics are permitted. This does NOT make upstream Worker delivery verified.
- Existing public Compose fail-closes paid source details (`VALYQON_RESTRICT_PAID_SOURCE_DETAILS=true`), and public AI is off unless specifically enabled. Do not disable the paid lock merely to display tender details.
- `compose.public.yaml` uses a **single-node SQLite** data volume. This is not a multi-replica production platform. PostgreSQL and backup/restore evidence are required before meaningful customer onboarding.

## Evidence gates and blockers

| Gate | State | Actual evidence needed |
| --- | --- | --- |
| GitHub code/CI | Partial | Exact main-based release candidate has Linux, Windows, Docker, PostgreSQL 16, Chromium and security tests |
| Trusted HTTPS endpoint | **NOT VERIFIED** | Real hostname, DNS A/AAAA, public listener 443, trusted TLS cert, secure response headers and health |
| Official tender freshness and delivery | **NOT VERIFIED** | Source notice on approved official URL → adapter → Worker → durable DB → user-owned match and alert/receipt; 0 duplicate runs |
| Registration and password reset | **LOCAL TEST ONLY** | Actual hosted HTTPS sessions, verified external email sender and controlled deliverability check |
| Subscriber paywall | **BLOCKED** | Merchant-signed webhooks, ownership/expiry/cancellation, refund ledger, tenant entitlements, fail-closed tests |
| AI document and search analysis | **NOT VERIFIED** | Configured model/CA and real inference with privacy and paid access policy |
| Tenant security | **TESTED LOCALLY** | Full live HTTPS negative authorization, CSRF, request size, rate limiting and separate company/workspace checks |
| Data persistence / restoration | **TESTED IN CI** | Encrypted on-host backups, restore rehearsal, retention and incident runbook on real server |
| Monitoring and notifications | **PARTIAL** | Opt-in → actual source match → customer-authorized email/Telegram delivery with real provider receipts |
| Legal/customer operation | **OWNER ACTION** | Appropriate legal seller, privacy policy and consent, billing and customer support obligations |

A green HTTP `/health` check or localhost Docker image does not satisfy this table.

## Public website policy
1. Only claim source coverage with actual current source evidence; don't show decorative procurement totals as measured market KPIs.
2. Unpaid/public users see redacted guest results only. Paid source details remain restricted until real entitlements exist.
3. Never expose `.env`, passwords, tokens, SMTP keys, merchant secrets, raw buyer documents or production customer rows in GitHub Actions.
4. Only Caddy exposes 80/443. FastAPI, Worker, PostgreSQL, Mailpit and internal RAG ports remain private.
5. Do not publish the local browser review ports 18765/18865, or promote their isolated fixture databases.
6. Do not start Telegram polling using a token if another polling process already exists.
7. No automatic production migration, DNS change, container replacement, volume deletion or notification send in CI.

## Safe operator run order once domain and authorized VPS access are configured
1. Validate the reviewed candidate and its release tests; produce a signed/tagged rollback point.
2. Prepare an isolated staging stack with PostgreSQL, encrypted backup, HTTPS, configured SMTP and source workers; **never reuse existing customer volume or secrets in CI**.
3. Accept actual official notices and E2E user alerts with consented synthetic accounts and current source links.
4. Manually inspect secrets and DNS on the trusted server (print only YES/NO statuses). Securely set `TENDERLENS_DOMAIN` and `ACME_EMAIL` there, not in source code.
5. Deploy Caddy/API first using reviewed production Compose with complete policy configuration; run `python scripts/verify_public_https.py --url https://YOUR-ACTUAL-DOMAIN` from an external network. This script is **read-only**, validates actual HTTPS and never reports commercial readiness.
6. Release registration and paid features only after email/merchant/source gates, controlled abuse and backup restore pass. Monitor errors and have rollback rehearsed.

## Required external setup
The repository does not provide a verified public hostname, current VPS SSH session, production DNS proof, external mail transport, merchant integration or live customer notification evidence. Those cannot be generated from GitHub source changes alone.

**Production deployment status: NOT PERFORMED. Commercial release: BLOCKED.**
