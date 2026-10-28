# Resend → VALYQON signed delivery-outcome observability (staged only)

## The concrete application gap

SMTP acceptance only means that Resend received an email, **not** that Gmail delivered it. Existing VALYQON auth endpoints issue a verification/reset ticket and hand it off synchronously, while asynchronous Gmail `550 5.7.1 ContentRejected` events are visible only in the Resend dashboard. This optional endpoint makes subsequent delivery **outcome events** observable to server operators without publishing an email address, ticket, reset URL, or SMTP key. It is **not** a Gmail deliverability fix.

## Default and security

- New route: `POST /api/v1/webhooks/resend`. It returns 404 and does nothing unless an operator explicitly provisions `VALYQON_RESEND_WEBHOOK_SECRET` with the genuine Resend webhook signing secret.
- Verify **raw body bytes** with Svix `svix-id`, `svix-timestamp`, and `svix-signature`; reject missing/invalid signatures and stale/future timestamps (±300 seconds). Bounded streaming body (64 KiB). No new dependency, network call or API key.
- Log **only** `kind=verification|password_reset` and `outcome=email.sent|email.delivered|email.delivery_delayed|email.bounced|email.suppressed|email.complained` for two recognized transactional subjects. Never log addresses, tokens, Message-ID, raw payload or bounce response.
- This diagnostic is **telemetry only**, not an account state mutation. Duplicate signed deliveries within the timestamp window could yield duplicate log entries; do not use the logs as an exactly-once ledger or infer inbox placement from `email.delivered` alone.

## Activation (future separate approval)

After code CI and independent review, in an **isolated, disposable** HTTPS preview only, provision a Resend webhook signing secret through the existing protected secret manager. Configure an explicitly approved Resend webhook endpoint with the documented `email.sent`, `email.delivered`, `email.delivery_delayed`, `email.bounced`, `email.suppressed`, `email.complained` events. Do not commit or print the secret or send test mail without a separate explicit operator authorization.

For current production, **DO NOT activate the webhook, enable SMTP, bypass legal registration, change Caddy/SQLite/users or deploy based solely on this PR**. Existing Gmail `550 5.7.1` problem still requires Resend deliverability/reputation remedy (or an operator-owned domain) plus separate real recipient acceptance; `VALYQON_EMAIL_MODE=disabled` stays the last confirmed state.

Rollback: unset `VALYQON_RESEND_WEBHOOK_SECRET` in an isolated environment; the route returns 404, no DB schema or account state has changed. Remove any preview webhook subscription from Resend under separate authorization. Current live provider reports **no webhook endpoints**, so historical bounces cannot be replayed into this newly staged route.
