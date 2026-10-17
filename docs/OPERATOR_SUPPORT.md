# Opt-in operator tenant support diagnostics

`VALYQON_OPERATOR_PANEL_ENABLED=1`, `VALYQON_OPERATOR_SUPPORT_ENABLED=1`,
`VALYQON_SUPERADMIN_ACCOUNT_ID`, and exact SHA256 of the verified operator e-mail are **all**
required. Disabled-by-default service will respond 404. Wrong or unauthenticated operator
gets 403/401. Reuses `app/api/operator_routes.py`'s exact verified-account credential policy.

- `GET /operator/tenants` paginated safe HTML, `GET /api/v1/operator/tenants?after_id=0`
  paginated API. Max 25 rows, bounded cursor, read-only SQL, no customer account e-mails,
  tender/PDF content, private team notes or provider secrets.
- Each organization row: member count, companies, historical recorded searches, saved
  tenders, opted-in alert preferences, recorded sent/failed receipts and support count.
  Recorded sent receipts **cannot** prove end-to-end provider receipt in the customer's inbox.
- Billing and subscription status is explicitly `billing_not_implemented`.
  No administrative mutating APIs are provided.
- Operator views emit safe `operator.tenant_list_read` application logs without client PII,
  but log retention is **external configuration**, not an immutable audit database.
- Logs, notification pipeline and subscriptions still require actual hosting, credentials and
  legal seller information. This does **not** activate payment collection or verify SMTP/Telegram.
