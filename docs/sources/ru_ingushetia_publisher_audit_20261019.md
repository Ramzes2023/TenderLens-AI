# Ingushetia procurement publisher evidence audit — 2026-10-19

## Finding, with confidence boundaries
**Verified:** the Ingushetia state procurement committee publishes federal 44-FZ EIS notices. Accredited electronic marketplaces reproduce those numbered notices. The local buyers actually conduct a large volume of procurements.

**Verified historically, not for the current year:** public buyers in the republic were instructed to choose among different electronic shops for small purchases. A March 2022 report states 27 government agencies had registered in different marketplaces and explicitly quotes the right to choose. This does NOT identify a 2026 universal small-purchase platform.

**Not demonstrated:** a separate republic-wide, native first-party source offering an anonymous list/API of new tender announcements. The research found no *verified* independently published regional procurement feed. We cannot prove the absolute nonexistence of one, nor claim that Ingushetia has zero additional municipal or corporate publishers.

Inventory verdict: INDEPENDENT_REGIONAL_SOURCE_UNVERIFIED (not CONFIRMED_ABSENT).

## Direct references
- Ingushetia government (2026-01-23) 2025 activity summary: 3,769 procurements, RUB 13.8bn; https://ingushetia.ru/news/na_goszakupkakh_v_ingushetii_v_2025_godu_sekonomleno_bolee_200_mln_rubley/
- Official federal EIS committee entity: https://zakupki.gov.ru/epz/organization/view/info.html?organizationCode=01145000008
- Magas municipality links to federal EIS as its tender destination: https://admmagas.ru/
- March 2022 regional account of different low-value marketplaces: https://gazetaingush.ru/news/v-ingushetii-zakupki-malogo-obema-do-100-tys-rubley-perevedeny-v-elektronnyy-format
- Federal Treasury on EIS statutory function: https://piter.roskazna.gov.ru/gis/edinaya-informacionnaya-sistema-v-sfere-zakupok

## Direct Ingushetia examples on accredited Fabrikant (mirrors, not separate EIS originals)
- https://soap4.fabrikant.ru/44/procedure/ea21/0114500000826002121 — federal 44-FZ ID 0114500000826002121, stationery, 223722 RUB; organizer Ingushetia State Procurement Committee, INN 0608058533, published 2026-09-04.
- https://soap4.fabrikant.ru/44/procedure/ea21/0114500000826002117 — ID 0114500000826002117, vehicle tyres for ambulance station, 274438 RUB; same organizer, published 2026-09-01.

These genuine official older records prove public first-party tender cards exist on an accredited marketplace. They are NOT fresh October notices, proof of a working continuous adapter, or permission to send archived tender alerts.

## Observed code path failure
Live hosted Ubuntu test 2026-10-19:
https://github.com/Ramzes2023/TenderLens-AI/actions/runs/39249317571

Result: ConnectorTransportError; cause chain ConnectTimeout, ConnectTimeout; retryable=True. Previously pinned trusted root was checked and scoped only to EIS, without disabled verification, but no HTTP response was obtained. Thus evidence supports runner-network reachability as blocker, NOT a TLS certificate failure, RSS status, or parser mismatch. Initial run similarly failed: https://github.com/Ramzes2023/TenderLens-AI/actions/runs/39248762609

PR #215 says local Russian Windows diagnostic fetched 10 each from 44-FZ/223-FZ RSS; those are a different environment, not the successful integration or delivery of this PR.

## Merge acceptance
1. Inspect the exact live query and genuine HTTP status on the deployment network or an authorized Russian Windows runner; no insecure proxy, TLS bypass, synthetic live response, credentials or login scraping.
2. Confirm original EIS 44-FZ law and source-owned regional evidence, not merely regions=06 URL argument.
3. Fetch two independent real original notice cards (or accredited first-party mirrors with explicit original EIS number), and check titles/organizer, not only response 200.
4. Real leased/fenced Worker, temporary SQL persistence, actual tenant keyword search, idempotent replay, cross-EIS alert dedup. Confirm Telegram actual acknowledged delivery in an authorized isolated staging environment.
5. Keep region source disabled and PR draft while mandatory live acceptance is blocked; don't label mirrors independent and don't call an EIS network timeout a passing source.
