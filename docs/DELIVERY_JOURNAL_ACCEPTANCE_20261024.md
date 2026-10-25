# VALYQON delivery journal — functional scope and evidence

## Completed (PR #281)

The authenticated **Notifications** page reads persisted `deadline_alert_receipts` through a company- and account-scoped API:

`GET /api/v1/organizations/{organization_id}/deadline-alerts/history`

The endpoint returns at most 50 latest delivery attempts for the authenticated account and **active** company, after both existing active-company authorization and an independent DB membership check. Response has private/no-store cache control. Returned fields are a minimal channel/state/lead-hour/timestamp snapshot and an internal `saved_id` only when the notice still belongs to the same company. Source IDs, original tender URLs, emails, Telegram chat IDs and tender prices **never appear in the journal payload**.

The user can refresh, see actual sender-return success/error/pending counts, navigate to their own Saved tender using the existing scoped authorization, and inspect an honest empty/error state. Refresh never sends a reminder. Deleting a saved tender does not falsify the recorded receipt; the deep link is omitted.

No change was made to the worker's alert delivery algorithm or to the notification-preferences endpoint, and no new database migration is required. The worker↔API import cycle found by isolated test collection was fixed by deferring the `TenderDiscoveryItem` schema import until `run_once`.

## Evidence

- Real temporary SQLite data: account and company isolation, missing membership denial, bounded history, persisted statuses and removed saved notice reference.
- Real API handler: authenticated account, active-company selection and `Cache-Control: private, no-store`.
- Node syntax + existing deadline worker regression tests.
- Chromium to authenticated ASGI handler to disposable SQLite, browser refresh, saved-link deep-link and outsider rejection; fixture receipts are **OFFLINE_FIXTURE**, not external SMTP/Telegram proof.
- Full Linux/Windows/Docker CI on branch's exact head required before accepting this PR.

## Strong limitations (still NOT VERIFIED)

`state=sent` means the configured sending callable returned without raising. It does not prove that the external provider accepted the message, that the inbox received it, or that it was read.

`pending` and `failed` receipts are durable records but **there is no verified retry/lease-recovery mechanism** in the existing deadline worker. The journal intentionally does not claim automatic retry or send new notifications.

This does not create a full inbox, unread counts, push messages, official source metadata revisions, external email/Telegram acceptance, merchant payments or billing-backed subscriptions.

## Next acceptance gate

To claim dependable tender alerts, independently implement/test capped retries with durable attempt counts, explicit backoff and safe leases, concurrency/idempotency under worker crashes, provider-recipient acceptance evidence, configured opt-in from a verified user, successful real source→Worker→DB→delivery, and tenant/privacy control. Do not infer this evidence from Mailpit password-reset delivery or a fixture-only browser test. No merge or production deploy until acceptance.
