# EIS 44/223 original-detail deadline: Stage 5 (2026-10-30)

**Status: STRICT READ-ONLY LOCAL PROBE, NO PUBLIC DEPLOYMENT.**

## Confirmed upstream facts from operator's completed Stage 4

- From operator Windows, official `/epz/order/extendedsearch/rss.html` returned
  12 canonical RSS entries per law. Both RSS groups lacked a usable explicit
  tender-specific bid deadline: `deadline_missing=12` for 44 and for 223.
- The suffixless `/rss` candidate returned HTTP 404. It must not be used as
  the default when the publisher supplies the working `rss.html` route.
- A single 44-FZ official original detail was independently accessible with
  a safely future closing date. One 223-FZ individual original returned
  HTTP 434; do not reclassify this publisher response as valid procurement data.
- Windows-local success does not resolve the **VPS host and Worker-network
  TCP timeout** to `zakupki.gov.ru`. The already-running V6 Worker has no
  current EIS entries or jobs in its isolated SQL database.
- The existing first-party RU runner remains offline; the operator has not
  approved a continuously available Russian collector route.

## New isolated implementation

- `app/sources/eis_official_detail_deadline.py` extracts only a uniquely
  labeled explicit closing clock from **visible official notice-body HTML**.
  It checks canonical RSS notice identity, exact official HTTPS detail path
  and aligned `regNumber`; scripts and off-origin data are excluded.
  It never infers the closing date from RSS publication time, a generic
  search form or another notice.
- `scripts/ru_eis_detail_deadline_live_probe.py` independently fetches
  official 44/223 RSS followed by up to three canonical individual details
  per law, using the existing SHA256-pinned Russian CA and audited direct
  HTTPS bounded transport. It sends no requests to unaudited origins and
  prints only aggregate counters, never titles, URLs, purchase numbers,
  customer information, credentials or full exception messages.
- `tests/test_eis_official_detail_deadline.py` protects against hidden script
  text, foreign origin, wrong law, invalid/expired dates, missing or
  conflicting deadlines and publication-time contamination.
- The EIS isolated offline-bridge workflow runs these tests, separately from
  actual live gates. **Offline success is not source evidence.**
- This module is **not automatically wired into production adapters**.
  Real first-party HTML needs verified response type and strict upstream
  identity before a source-specific, opt-in production enrichment change
  may be reviewed.

## Release blockers in strict order

1. Prove 44 and 223 individually from accessible current original details,
   including canonical ID and future submission deadline. HTTP 434 must
   remain blocked; no arbitrary User-Agent, proxy or CAPTCHA workaround.
2. Operate a reviewed continuously reachable publisher egress. Operator
   Windows/WSL is suitable for a bounded investigation, **not proof of a
   reliable always-on server**.
3. Verify exact Worker image and egress on the intended isolated production
   runtime, with safe credentials, volume backup and tested rollback.
4. Produce authentic same-Worker original notice -> durable isolated
   SQLite -> accepted current deadline -> keyword guest query -> public HTTPS
   proofs for each explicitly enabled law. Protect production tenant data,
   current Caddy routes, source dedup and customer notification consent.
5. Only then merge the reviewed source release and activate it.
   A CI green fixture or a single HTTP 200 is not enough.

**EIS_PUBLIC_DEPLOYMENT=NOT_PERFORMED**
