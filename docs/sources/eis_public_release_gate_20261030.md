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


## Implemented isolated public EIS bridge (additional change in this PR)

This PR now contains an **optional operational path**, not merely live probes:

- `ops/public_sources/compose.eis-rss.yaml`: separate 44-FZ and 223-FZ official RSS URLs, mandatory operator-provided, never from company keywords; direct validated TLS; both disabled until explicit overlay activation.
- `app/api/isolated_public_sources.py`: public-source allowlist flags for `eis`, `eis_223`; default off.
- `app/sources/isolated_public_scheduler.py`: on explicit operator flags, verifies same-host fixed RSS URLs and enqueues only selected official keys on the existing bounded hourly Worker. Existing nine pre-approved Russian sources remain unchanged. Both EIS keys are **not** reclassified as previously verified.
- `app/sources/eis_deadlines.py`, `eis_rss.py`, `eis_223_rss.py`, `app/api/public_source_deadline.py`: result-level closing clock can be used only if explicitly published by the source. Unknown timezone is never guessed: conservative UTC+14 current-deadline criterion; unknown deadline is excluded from live guest results.
- `app/api/public_eis_identity.py` and guest search enforce official HTTPS host, explicit 44/223 path and aligned registration number for visible candidates. Guest projection still hides originals, buyer, number and protected source details. Existing paid-source lock remains enabled.
- `app/sources/eis_vps_acceptance.py`: same-isolated-Worker real upstream diagnostic, requiring separately genuine currently open 44 and 223 originals, without SQL writes or customer data. It reports **candidate only** even on green.

### Trusted operator rehearsal (DO NOT run against the main production Compose)

The existing six-source isolated public stack must already be verified, including source volume backup, exact image digest and safe Caddy rollback. Put reviewed official 44 and 223 RSS URLs in **operator environment only** as `VALYQON_EIS_44_RSS_URL` and `VALYQON_EIS_223_RSS_URL`; never commit them alongside personal access tokens. Both URLs must be the official `https://zakupki.gov.ru/epz/order/extendedsearch/rss.html` endpoint, appropriately filtered to one law.

With the reviewed exact image installed into an **isolated trial project/volume** and all six source overlays applied in existing order, add `-f ops/public_sources/compose.eis-rss.yaml` last to each corresponding Compose call. First validate `docker compose ... config --quiet` and confirm no production DB mounts, automatic bot sends or new ports.

Before scheduling, run the read-only check from the **isolated trial Worker**:

```bash
docker compose -p valyqon-public-sources \
  -f ops/public_sources/compose.yaml \
  -f ops/public_sources/compose.south-ural.yaml \
  -f ops/public_sources/compose.kavkaz-rf.yaml \
  -f ops/public_sources/compose.lenobl.yaml \
  -f ops/public_sources/compose.samara-list.yaml \
  -f ops/public_sources/compose.eis-rss.yaml \
  exec -T worker python -m app.sources.eis_vps_acceptance
```

Pass requires `EIS_VPS_ACCEPTANCE=CANDIDATE_ONLY`, meaning genuine official current notices were fetched; **it does not prove** durable queued work, SQL search, deployment or HTTPS. On any nonzero result, keep EIS off and diagnose the transport in that exact VPS environment.

Then explicitly enqueue exactly each accepted EIS source in a disposable trial, using `docker compose ... run --rm --no-deps enqueue python -m app.sources.enqueue --source eis` and the corresponding `--source eis_223` command. Check each returned job's `succeeded`, fresh original ID + deadline and SQL row, cross-platform duplicate handling, anonymous projection, loss of upstream and absence of unintended alerts. Only after independently verified guest HTTPS match and rollback may the reviewed EIS overlay join the already deployed isolated public stack. The verified scheduler profile is a separate later opt-in. **Do not** enable EIS on `tenderlens-vps` or alter the base production customer DB.

### Long-term official machine-readable feed

The 2025+ officially described SOI service is **not** implemented by this RSS overlay. The operator must acquire lawful registered service access and current official TFF schema (getDocsLE2 for organisations or other appropriate interface), develop a separately tested signed/token-authenticated SOI connector, validate 44/223 XML data and documents, check access/retention conditions, then run a real Worker → SQL → user acceptance. Never disguise scraped RSS or marketplace mirrors as an official authenticated SOI result. No token is currently available to this PR.

**Current claim: IMPLEMENTED_GATED_STAGING_ONLY; EIS_PUBLIC_DEPLOYMENT=NOT_VERIFIED.**


### Exact EIS Worker → isolated SQL release audit (read-only)

After the **separately validated real first-party fetch** and explicitly submitted EIS 44+223 jobs, run **inside the isolated Worker**:

```bash
docker compose -p valyqon-public-sources \
  -f ops/public_sources/compose.yaml \
  -f ops/public_sources/compose.south-ural.yaml \
  -f ops/public_sources/compose.kavkaz-rf.yaml \
  -f ops/public_sources/compose.lenobl.yaml \
  -f ops/public_sources/compose.samara-list.yaml \
  -f ops/public_sources/compose.eis-rss.yaml \
  exec -T worker python -m app.sources.eis_isolated_runtime_audit
```

The audit reads source-opportunities and durable connector jobs through SQLite `mode=ro` and `PRAGMA query_only=ON`, never opens the main production DB, never prints procurement contents or registered recipients, and never triggers notifications. For **each** law it requires a fresh successful connector job, a positive accepted notice count, a recent official canonical source record, a verified future submission deadline and the safe public-preview allowlist. `EIS_ISOLATED_SQL_WORKER_AUDIT=CANDIDATE_ONLY` means only **isolated Worker/SQL local readiness**. It is NOT proof of authentic current upstream access, external HTTPS/Caddy routing or an active customer-facing integration. Failures return a nonzero status and must block the public cutover.

**Additional release gate:** after source-specific trial acceptance, verify the public-domain `/api/v1/public/opportunities` route is in fact reading the intended isolated source volume, not the legacy API DB. Match a synthetic-free live result using its title through a separately authorized read-only audit; no identifiers or purchaser details can be published in anonymous previews. Test rollback to the previous six-source Compose layers without losing the original public site. Keep `valyqon-public-sources` Compose name illustrative: always confirm the actual current operator project/name before applying any command. Never run these as generic production migrations.
