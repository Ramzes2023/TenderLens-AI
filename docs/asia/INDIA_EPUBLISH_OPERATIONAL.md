# India ePublishing government tenders — operator guide

The official Government of India **Central ePublishing System** on
`https://eprocure.gov.in/epublish/app?service=home` is a different platform
from the existing `india_cppp` eProcure connector. It displays **Latest
Tenders**, distinct from **Latest Corrigendums** and contract awards. Its
government listing rotates frequently; this connector reads only verified
individual tender entries in the Latest Tenders section.

**Limits:** one public HTML GET, no login, no CAPTCHA solving, no pagination,
at most 20/100 returned notices by configured cap; no guessed publication date,
budget or buyer. The website's individual detail HREF contains temporary
`session`/`sp` tokens; **never persist or share those ephemeral links**.
A saved record includes the stable official homepage URL, full public Tender
Reference Number and exact published closing date. Users find the tender by
its reference number on the linked government site. This is **not** a stable
direct deep link to an individual tender. Treat the displayed deadline as
published on the source and reconfirm with the issuing authority before bidding.

## Activation on the trusted host only

After mandatory PR-hosted real upstream → queued lease-fenced Worker →
isolated SQLite → searchable public snapshots gate, the adapter is
**registered only if** `VALYQON_ASIA_INDIA_EPUBLISH_ENABLED=1`.
It remains disabled by default. It uses the same independently configured
durable queue and database as the service. Production must explicitly enable
the flag, start/supervise `python -m app.jobs.worker --connectors`, enqueue
`ConnectorSyncService.enqueue("in_epublish")` from a trusted hourly scheduler,
and monitor failures and stale listings; this PR does not install those
production processes. Company-scoped snapshot search remains governed by
existing tenant authorization, rather than any unauthenticated public endpoint.

## Research exclusions

China CCGP official list HTTP 403 from GitHub-hosted probes;
Mongolia `tender.gov.mn/mn/invitation` HTTP 403; Turkish EKAP public search
could not establish a usable anonymous response. Korea KONEPS official
REST API requires an authorized data.go.kr key; Mongolian official open data
API requires a Bearer token. None of those research candidates is registered,
counted as working, or bypassed using credentials/challenges in this PR.

**No production DB, AWS, account, notification delivery or scheduler changed.**
