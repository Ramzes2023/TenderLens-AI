# VALYQON AI — functional acceptance, evidence first (2026-10-24)

Current candidate: draft PR #264, not main. Never deploy or merge based on this file.

## Evidence tiers

- **C1: Static and unit/contract CI**: tests and Docker/Windows/PostgreSQL 16 jobs must be green for **the exact PR head**. This does not prove a browser or upstream source is working.
- **C2: Authenticated API integration, isolated DB**: `tests/test_authenticated_team_source_roundtrip.py` exercises actual FastAPI auth sessions, team PATCH, second-user approval, audit, cross-origin rejection, cross-tenant rejection, and two EIS metadata observations, all `OFFLINE_FIXTURE`. It does not prove Chromium or real EIS uptime.
- **C3: Local review HTTP**: `ops/website_preview/smoke-functional.ps1` performs only read-only, unauthenticated requests to loopback 18865 and Mailpit 18866. No accounts, email sends, source fetches, or payments. Its green result is **not** C4.
- **C4: Authenticated real-browser use**: Codex/QA operator tests a disposable account in an isolated QA Docker database, using a real Chromium instance and records actions, responses and redacted screenshots. Review 18865 has no upstream workers; only test fixtures are legitimate in an **explicitly separate** ephemeral QA environment.
- **C5: Real upstream / financial / messaging acceptance**: Independently check live platform → adapter → Worker → durable DB → query → authorized user delivery, source identity, original official URL, deduplication, notification receipt. Only send to controlled operator test recipients. Verify provider-backed payment entitlement, not frontend badges. These steps cannot pass in isolated review.
- **C6: Deployment/restore readiness**: independent PostgreSQL backup/restore and data import, security scan, TLS/merchant configuration, dedicated user acceptance on candidate build.

## Feature-by-feature expected result

| Feature | Proof necessary before release | Known boundary |
|---|---|---|
| Registration/login/reset | Browser and API; Mailpit shows local reset message; unknown account non-disclosure | Mailpit is not external Gmail/SMTP |
| Workspace, company, roles | Owner/member/viewer tests; switch tenant and deny stale requests | Different from one-person smoke |
| Find and Save | Real official notice and exact tenant-scoped persisted record | Empty isolated review is normal |
| Board stages | Save → card → change stage → refresh → persisted; revision collision 409 | Internal stage is not official bid submission |
| Assignee/approval | Owner assigns, member requests, different owner/admin approves, audit persists; same requester 403 | No bid submission |
| Source change history | Two authentic worker EIS versions with changed title/price/deadline; no history when absent | PDF document diff and proactive alert not yet built |
| Buyer charts | Real company saved customer names, no cross-tenant counts | No verified competitor/winner rankings |
| Calendar | date-only and timezone-aware deadlines, filter, month navigation, valid manually exported ICS | No Google/Outlook auto sync |
| Notifications | Opt-in → worker → receipt → controlled test Telegram or SMTP provider | Mailpit reset email alone is not Telegram acceptance |
| Paid content and billing | Unpaid guest has no buyer/source URL, real payment webhook-entitled account only gains access | Review deliberately disables merchant checkout |
| API/AI | Auth, limits, provider config, actual response from verified provider | Review intentionally disables AI |

## Release gate
No merge until C1–C4 and relevant C5/C6 evidence is available, the exact commit is green, no data leaks/privilege escalation are seen, and there is an explicit change review. Treat missing evidence as **NOT VERIFIED**, not as **PASS**. Never insert invented real-looking tenders into a customer database, or copy credentials/tokens into GitHub logs.

## Operator
See `ops/website_preview/QA_CODEX_PROMPT_RU.md`. The user only needs to open Codex in the existing review worktree and paste this task. For browser QA no live external sources are enabled and no production Docker volumes are used.
