# ЕИС 44-ФЗ / 223-ФЗ → публичный VALYQON: проверяемый путь подключения

30 October 2026. This is an **actual-source test gate**, not a deployment or an assertion that EIS is connected to `https://valyqon.duckdns.org/`.

## Current mainline reality
- EIS RSS 44-FZ: `app/sources/eis_rss.py` (key `eis`) builds filtered official RSS requests. Historical first-party probe produced HTTP 404 on the referenced routes. A configured search filter is **not** proof of 44-FZ legal identity or live tenders.
- EIS RSS 223-FZ: `app/sources/eis_223_rss.py` (key `eis_223`) independently checks observed law, protects against 44/223 cross-contamination, and needs a real feed.
- EIS 44-FZ HTML: `app/sources/eis_44_public_html.py` (key `eis_44_html`) extracts exact official listing cards. It is *listing-only*; individual official detail pages were **not** independently verified from the probe host. This adapter currently does not expose a validated future submission deadline.
- Both the legacy public website API (`compose.public.yaml`) and the isolated six-source public feed (`ops/public_sources/compose.yaml`) keep EIS adapter flags **off**. The isolated API allowlist and scheduler expressly cover only the approved Russian six-source sequence. Setting one EIS env flag is **not** a completed integration.
- The currently staged six sources are MikroTon, STAN commercial, South Ural, Kavkaz.RF, Lenobl and Samara public list. Their Docker overlays in main **do not prove** that the deployed VPS/Caddy is serving them.

## Newly runnable strict official-live probes

GitHub Actions workflow `.github/workflows/ru-eis-official-real-worker.yml` has two independent real public-fetch jobs:

1. EIS 44-FZ HTML: pinned Russian CA → official HTTPS card → existing connector handler → **temporary SQLite** → original ID / keyword search and repeat-insert idempotency; fails red if real fetch is unavailable. Individual detail links remain unverified even on green.
2. EIS 44/223 RSS: pinned Russian CA → both real feeds → separate temporary SQLite + search. `VALYQON_RU_REQUIRE_EIS_LIVE=1` forces a non-zero exit if either EIS adapter is unavailable or returns no usable real notices. The extra B2B observation is *not* a pass requirement.

The test job never runs an application deployment, never mounts production volumes, never reads private company databases, never bypasses TLS or anti-bot checks, and sends no mail or Telegram messages. No offline test fixture can turn a failed live test green.

**A red live gate must remain red**; do not change it to success on empty, stale, mocked or transport-blocked data.

## Go/no-go for actual public activation

1. Require current official EIS 44/223 upstream transport and publication/identity proof from a *relevant* network vantage point, not only an unrelated GitHub runner. Confirm legal category, price/currency and an independently verifiable **future** submission deadline before claiming active open tenders.
2. Independent official detail page / list-only limitation must be shown honestly. Don't conflate platform mirrors with independent 44/223 procurement identities. Keep both original IDs and cross-source provenance.
3. Build *separate, default-off* EIS isolated-worker and public-feed allowlist/scheduler changes under review. Re-run `tests/test_ru_eis44_public_html.py`, source-owned real CI, worker/SQL, dedup, tenant authorization and guest projection tests. Do not add an unverified EIS source to the six-source production allowlist.
4. On trusted VPS, read existing running project/image/Caddy routes, source-worker receipts, health, original URL and latest safe deadline; snapshot/restore isolated SQLite; prove worker → DB → keyword guest API. Preserve old API/database and Telegram.
5. Only then stage the *exact* new image against `valyqon-public-sources`; perform the limited Caddy route cutover under the existing `docs/sources/isolated_public_source_site_rollout.md` procedure and verify external HTTPS and rollback. No production Caddy or billing changes from this PR.
6. Customer Telegram alert delivery requires a separately authorized source-to-subscription pipeline and explicit user consent. A live source does **not** authorize sends.

## Current verdict
**EIS_PUBLIC_ACTIVATION = BLOCKED_PENDING_LIVE_UPSTREAM_AND_RELEASE_GATES.**

The strict diagnostics deliberately expose the reason rather than manufacturing a successful integration. Code merge, runtime source activation, publishing external HTTPS results, and consented alert delivery remain four distinct milestones.
