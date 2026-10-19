# VALYQON AI — Russian source prelaunch queue (manual only)

This is an **operator-owned** runbook. It does not authenticate to any ETP,
run periodically, start a Worker, deploy to AWS, modify production configuration,
or claim that every Russian research card is a working procurement adapter.

## Approved original-source pipelines

The opt-in `--ru-approved` batch contains exactly seven existing independently
live/Worker-tested adapters: `b2b_center`, `lenobl_small_public`,
`nmck_native_public`, `mikroton_tender`, `south_ural_public`,
`stan_commercial_public`, `kavkaz_rf_firstparty`. Buyer-owned postings
are **not necessarily independent unique procurement publishers**; EIS and
marketplace cross-posts must not count as extra unique opportunities.

This allowlist intentionally **excludes** open/failed research and unverified
transport (`tektorg`, `gpb_etp_public`, `roseltorg`, `fabrikant`,
regional research cards); EIS RSS requires its own verified feed and flag.

## Pre-launch operator steps

1. Review the seven live acceptance workflow runs again on the **deployed SHA**.
   Check uptime, current original notice links, matching buyer/price and
   same-host access. A green historical CI alone does not guarantee a live feed
   today. Confirm cross-feed dedup, acceptable query volume and credentials
   restrictions; never bypass anti-bot or region restrictions.
2. On the operator-managed host only, explicitly set each desired source's
   standard default-off switch (no blanket flag):
   `B2B_CENTER_ENABLED`, `LENOBL_SMALL_PUBLIC_ENABLED`,
   `NMCK_NATIVE_PUBLIC_ENABLED`, `MIKROTON_TENDER_ENABLED`,
   `SOUTH_URAL_PUBLIC_ENABLED`, `STAN_COMMERCIAL_PUBLIC_ENABLED`,
   `KAVKAZ_RF_FIRSTPARTY_ENABLED`.
   Keep blocked/research sources disabled.
3. Configure the normal environment and database. Run the existing connector
   worker separately with `python -m app.jobs.worker --connectors`.
4. Enqueue **once per current UTC hour** from the same authorized environment:
   `python -m app.sources.enqueue --ru-approved`.
   This only enqueues currently enabled allowlisted sources; it does not enable
   them, fetch network records in the CLI, start workers, or send notifications.
   Job identity includes source, UTC hour and connector version, so repetitions
   in the same hour return the same task identity.
5. Inspect returned job IDs, then query each with
   `python -m app.sources.enqueue --status <UUID>`.
   Confirm `succeeded`, valid first-party original IDs, stored snapshots,
   tenant-scoped keyword search and no duplicates before enabling customer
   delivery. If a source returns `permanent_failure`, leave that individual
   switch off until corrected and *re-tested*.
6. Telegram opt-in remains **separate**:
   `MONITORING_ENABLED=true` plus
   `VALYQON_RU_BACKGROUND_CATALOG_ENABLED=true` and each user's explicit
   monitoring subscription. The notification loop marks a notice seen only
   after successful Telegram delivery, but retries may duplicate a delivered
   message if the process crashes after sending and before recording the
   receipt. This is **at-least-once**, not exactly-once delivery.

There is **no automatic schedule** created by this PR, no cloud action and no
change to production payment, AWS settings or customer account data. A
production operator must explicitly validate the deployment and any schedule.
