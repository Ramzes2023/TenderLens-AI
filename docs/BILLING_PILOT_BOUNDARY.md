# VALYQON Company billing cabinet — pilot truth boundary

- Organization Billing navigation now displays a real role-checked API snapshot
  `GET /api/v1/organizations/{id}/billing`, restricted to owner/admin of a **shared**
  organization. Other account and personal workspace data is denied.
- Recorded searches, saved tenders and seats come from the database. These are
  historical workspace counters **not invoiced metering**.
- No verified subscriptions, plans, payment dates, transactions, invoices or legally
  valid closing documents exist in this integration yet. They are explicitly null,
  empty or disabled — NEVER demo money, false discounts or unsourced charge dates.
- The upgrade button is intentionally disabled. No front-end checkout, payment API,
  webhook, card capture or silent charge happens.
- Prior to real billing: select approved legal entity + seller jurisdiction, merchant,
  sign provider agreements, issue business accounting documents, implement signed
  webhook verification and idempotent payment ledger, invoice/receipt retrieval,
  refunds, failed-charge handling, signed recurring authorization and sandbox tests.
- This is an honest production-safe **cabinet foundation**, not a fully functioning
  merchant checkout. Do not promise customer payment readiness.
