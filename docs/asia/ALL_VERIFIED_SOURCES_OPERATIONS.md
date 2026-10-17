# VALYQON AI · Asian real-source operations, fifteen verified adapters

These fifteen sources were previously independently subjected to **real anonymous official
HTTPS → lease-fenced durable Worker → disposable SQLite → searchable snapshot** CI
acceptance. The unified operator CLI adds a safe batch control and search surface,
**not** a new upstream connector, AWS deployment or customer notifications.

## Current approved IDs

- Hong Kong, six procurement channels: `hk_ha_works`, `hk_ha_leasing`,
  `hk_emsd_tenders`, `hk_emsd_consultancy`, `hk_dsd_current`,
  `hk_cedd_tenders`.
- Hong Kong Highways Department: `hk_hyd_tenders`.
- Japan JETRO's **own** bids, not Japanese nationwide tenders: `jp_jetro_bid`.
- Hong Kong Monetary Authority public invitation notices from the official HKMA JSON API: `hk_hkma_tender`.
- India Central ePublishing latest tender opportunities: `in_epublish` (original reference and public list, not temporary detail URLs).
- UAE Ministry of Finance federal current RFQs: `ae_federal_mof` (actual government RFQ detail links; **not** Dubai or Abu Dhabi coverage).
- Türkiye Ankara Metropolitan Municipality open tender notices: `tr_ankara_municipality` (city government only, **not** all EKAP or Turkey).
- Türkiye ASKİ water and sewerage government current tenders: `tr_aski_water`, **separate** from city hall source.
- Singapore Government GeBIZ official *Business Opportunity* category RSS:
  `sg_gebiz_professional` and `sg_gebiz_misc`.

**Count:** 15 distinct connectors across 6 procurement jurisdictions (Hong Kong,
Japan, Singapore, India, the UAE and Türkiye), not 15 countries. All are disabled by default. Availability varies,
open bid status must be checked on the official website before bidding; archived
opportunities are not automatically expired or removed from local snapshots.

## Safe operator activation

Requirements on the **trusted target host**: configured same persistent database
for API, job Worker and operator CLI (PostgreSQL 16 or supported selected
database); migrations applied; direct outbound HTTPS to the official feed hosts;
approved process supervisor; logs and tenant authorization independently reviewed.

No secrets in GitHub, no untrusted PR workload on personal self-hosted runners.
Set these flags only in the verified environment where processing is intended:

```sh
VALYQON_ASIA_OPERATIONS_ENABLED=1
VALYQON_ASIA_SOURCES_ENABLED=1
VALYQON_ASIA_JETRO_BID_ENABLED=1
VALYQON_ASIA_HYD_ENABLED=1
VALYQON_ASIA_HKMA_ENABLED=1
VALYQON_ASIA_INDIA_EPUBLISH_ENABLED=1
VALYQON_ASIA_UAE_FEDERAL_ENABLED=1
VALYQON_ASIA_TURKEY_ANKARA_ENABLED=1
VALYQON_ASIA_TURKEY_ASKI_ENABLED=1
VALYQON_ASIA_GEBIZ_ENABLED=1
```

1. Safe read-only introspection, requires no DB or flags:

   ```sh
   python -m app.sources.asia_all
   ```

2. On the same trusted host and production-approved database, run and supervise
   the existing Worker continuously:

   ```sh
   python -m app.jobs.worker --connectors
   ```

3. Submit fifteen independently validated, idempotent current-UTC-hour queue jobs.
   Preflight validates **all fifteen** before opening the database. A single disabled
   source fails the batch, rather than silently lowering expected coverage.

   ```sh
   python -m app.sources.asia_all --enqueue
   ```

   For an independently configured individual source:

   ```sh
   python -m app.sources.asia_all --enqueue --source sg_gebiz_professional
   ```

   **Queued is not succeeded**. Use
   `python -m app.sources.enqueue --status <returned-job-uuid>` for job state,
   then inspect stored counts and exact official opportunity URLs.

4. Search previously ingested public tenders locally; no customer terms are sent
   to an upstream website:

   ```sh
   python -m app.sources.asia_all --search "equipment" --limit 20
   python -m app.sources.asia_all --search "engineering" --source hk_hyd_tenders
   ```

5. On the trusted host only, schedule the **same enqueue command** approximately
   hourly with an existing approved job scheduler, monitor completion/failure,
   and define alerting for missing records or stale feeds. This PR **does not**
   install or start any scheduler or production Worker. The queue enforces
   per-source/per-hour de-duplication. GeBIZ officially publishes only the most
   recently published open opportunities in its RSS: sync reliably, then match
   locally. Do not claim historical/full GeBIZ coverage.

6. The existing authenticated company-scoped
   `POST /api/v1/organizations/{organization_id}/discover/tenders?snapshots=true`
   reads stored public source snapshots if appropriate environment source flags
   are set; company profile keywords filter the matching records. Delivering
   push/email/Telegram alerts to customers requires separate audited customer
   subscription and notification configuration, not just enqueue and merge.

## Research excluded from source count

On 16 October 2026 a GitHub-hosted probe observed Hong Kong DSD separate
consultancy EOI feed HTTP 200 but **zero opportunities**; Singapore GeBIZ
Accommodation had one entry without a verified official detail link;
eight guessed GeBIZ category URLs returned HTTP 406. These were **not**
registered or counted as working sources. Additional sources require their
own real Worker/DB/query acceptance; no synthetic fixture may substitute for it.

## Production change policy

**PR CI uses only disposable databases and official anonymous feeds.**
Do not infer 24/7 operation from passing CI; no production env, AWS deployment,
customer data or schedules are modified by merging this code.
