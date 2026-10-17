# VALYQON AI — 15-point professional SaaS readiness audit (2026-10-17)

This is a code-level inspection of `main` at `479a3bc`, followed by the scoped changes in this PR. **Code green is not a production launch or live upstream proof.** No real payments, e-mail/Telegram delivery, official registry enrichment, browser acceptance, or vendor credentials are asserted.

| # | Requested capability | Assessment and evidence |
|---|---|---|
| 1 | Operator console: tenants, subscriptions, per-client usage and actions | **Partial:** `app/api/operator_routes.py` opt-in verified aggregate dashboard, no tenant drilldown, subscription mutation, or operator action audit. |
| 2 | Billing cabinet, invoices, payment history | **Missing:** shell Billing remains a placeholder. Cannot offer real receipts, invoices or checkout without provider merchant approval and legal operator details. |
| 3 | Team roles | **Implemented core:** `organization_members` owner/admin/member/viewer; scoped APIs and invitation flows. Role changes guarded. |
| 4 | Public uptime/status page | **Missing:** authenticated Source Health and `/health` exist, but a reliable historical uptime/public status service is not deployed. Never substitute 'configured' for verified online. |
| 5 | Help/knowledge base | **Partial:** `/how-it-works`, `/usage-guidelines`, Discovery scoring explanations. More transparent and localized user-facing reference needed. |
| 6 | Saved filter queries + daily new-tender digest | **Missing:** Discovery history and manual monitoring are not persisted filter subscriptions with daily delivery/dedup. |
| 7 | Buyer background checks (RNP, terminations, litigation) | **Missing:** no official registry verification and citations joined to a buyer; must not invent risk scores. |
| 8 | Explainable scoring | **Implemented core:** `scoring/preview.py`, `scoring/engine.py` and Discovery evidence/reason breakdown; unknowns remain unknown. |
| 9 | Tender workflow stages, team notes and audit | **Added by this PR:** active-company scoped persisted stages and private note; CAS revision, owner/admin/member writes, viewer read-only, durable stage-change audit. |
| 10 | Semantic tender search | **Missing as explicit tender vector index:** RAG on uploaded documents exists; not equivalent to semantic procurement catalogue search. |
| 11 | Public API/webhooks | **Partial:** authenticated REST APIs exist, but no managed per-client webhook subscriptions or outbound delivery signing. |
| 12 | SSO/SAML | **Missing:** email/password/session login. |
| 13 | Company audit log | **Partial:** the tender-stage audit in this PR does not equal full account-wide save/export audit. |
| 14 | Per-plan enforced quotas and rate limits | **Partial:** bounded synchronous admission and `quota_admissions`, not paid-plan entitlements. |
| 15 | Enterprise SLA/contract | **Missing:** operational SLA and legal/customer sign-off are external launch requirements. |

## Pilot-specific safety

- Company membership is independently checked inside every tender-workflow database operation. Viewers can inspect; they cannot write. Non-members cannot read another company’s status or notes.
- Stage is **operator-entered workflow metadata**, not an official tender outcome and not proof of submitting a bid; stage transitions have no side effects.
- Changes use an expected revision: two collaborators cannot silently overwrite each other.
- Audit entries store actor, stage change and timestamp, **never a second copy of private note text**.
- Deletion cascades to lifecycle and event rows. SQLite offline import has a verified schema signature; PostgreSQL 16 acceptance required before merge.
- No billing, registry, outbound webhook or tender submission is silently enabled.

## Next independently gated increments

1. Tenant-level operator support console with minimal PII, explicit permissions and audit.
2. Read-only billing overview, then **sandbox-only** checkout + signed webhook acceptance with provider's real credentials.
3. Persisted saved filter subscriptions and genuine new-notice digest with opt-in and throttling.
4. Public status from independent probes, with unknown/unverified components explicitly marked.
5. Official procurement buyer checks and semantic search only after source licensing and quality acceptance.

Never merge a feature with failed mandatory GitHub Actions gates or present a source as live without independent acceptance.
