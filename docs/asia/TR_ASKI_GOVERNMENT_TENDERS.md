# Türkiye — Ankara ASKİ official water-sector tenders

**Issuer:** Ankara Su ve Kanalizasyon İdaresi Genel Müdürlüğü (ASKİ),
official public tenders at `https://www.aski.gov.tr/tr/ihale.aspx`.

This is an official Turkish water and sewerage public buyer,
**not** the national EKAP index and **not** Ankara Metropolitan Municipality
main procurement list (separate source `tr_ankara_municipality`).
The official ASKİ list identifies seven recently open tenders, with
2026 KİK numbers, publication dates and closing dates. Individual
source detail links use fixed route
`https://www.aski.gov.tr/tr/IhaleDetay.aspx?ID={numeric-id}`.

The default-disabled source is `tr_aski_water`, enabled only when
`VALYQON_ASIA_TURKEY_ASKI_ENABLED=1`, using one official list GET and
at most four official detail GETs (five total within worker egress
budget). Every accepted row must have a verified individual government
detail, matching KİK number, unexpired exact official deadline, valid
publication date, title and approved HTTPS hostname. If detail is
missing or old, no bid is silently fabricated. The original
municipality detail documents control participation eligibility:
some notices explicitly allow **only domestic bidders**, and public
discovery does not imply the client can submit a bid.

## After genuine CI green

Use a trusted production host with the same persistent database for
API, queue and Worker; review migration status, permissions and outbound
HTTPS. Then enable the source flag and
`VALYQON_ASIA_OPERATIONS_ENABLED=1`. With the continuous
`python -m app.jobs.worker --connectors` running, a trusted operator
can submit an hourly idempotent job:

```sh
python -m app.sources.asia_all --enqueue --source tr_aski_water
python -m app.sources.asia_all --search "malzeme" --source tr_aski_water
```

Enqueue is not delivery; confirm job state, successful record storage
and authenticated customer snapshot retrieval. No automatic cloud
scheduler, email delivery or AWS deployment is created by this branch.
GitHub CI uses a disposable SQLite DB, actual government HTTPS, a true
leased Worker, keyword search and repeat enqueue idempotency. Do not
claim 24/7 production readiness from green CI alone.
