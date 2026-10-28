# VALYQON — staged real procurement sources → public site (operator runbook)

## Scope and limits

This change gives VALYQON a **separate public preview API** backed by a
**separate source Worker and isolated SQLite volume**. It cannot change the
existing website's user accounts, paid entitlement, Telegram, source archives,
production SQLite, registered company data or functioning isolated guest AI.

The old production Docker Compose project remains `tenderlens-vps`. Do not
include `ops/public_sources/compose.yaml` in its five-file stack or change
the old production API container/image. The **only** shared resource is the
already-existing, explicitly checked Caddy edge bridge network; the isolated
source services have no published host ports.

Base opt-in RU sources: `mikroton_tender` and `stan_commercial_public`.
Additional separately verified **opt-in overlays**, already present in `main` as
of 28 October 2026, are in fixed order: third `south_ural_public`, fourth
`kavkaz_rf_firstparty`, fifth `lenobl_small_public`, sixth
`ru_samara_public_list`. These are staged code, **not proof of deployment**.
The Samara sixth source is **official public LIST ONLY**, without independently
verified individual detail cards. An enabled flag is not an accepted live Worker
receipt or a user's actual HTTPS search result.
MikroTon is a commercial public procurement portal, not EIS; its API
has active and archived endpoints: https://tender.mt52.ru/api-docs .
STAN has published, separately verified **non-EIS commercial** originals
with actual bidding deadlines: https://stantorgi.ru/etp .
STAN's adapter expressly skips its 223-FZ / EIS-mirror items to avoid
double-counting those tenders as independent listings.
**An official site showing no active tenders must lead to a blocked cutover,
not sample/demo records or re-labeled archived procurement.**

Other RU adapters in main or unmerged branches are outside the six-source
isolated public configuration. Ingushetia, Chechnya, TEK-Torg, GPB, Fabrikant,
Roseltorg, Dagestan and CIS research PRs remain off until independent upstream
Worker, SQL, leak, dedup and freshness gates pass. No blanket activation.

## Operator verification before *any* cutover

1. On a trusted host, read-only inspect real Caddy config and Docker
   networks, production API image, original SQLite volume and available
   rollback. Preserve hashes/backup and a byte-identical current Caddyfile.
   The old `guest-ai` route MUST continue pointing to its working AI service.
2. Fetch the exact reviewed source commit into a **new** VPS checkout. Confirm
   branch/main did not move the build commit. Build the isolated image there.
   Its Compose project is `valyqon-public-sources`, not `tenderlens-vps`.
   Keep the Docker image pinned to its real build digest.
3. Start only the new private services (no Caddy change, no public route):

   ```sh
   docker compose -p valyqon-public-sources \
     -f ops/public_sources/compose.yaml up -d --build guest-sources worker
   docker compose -p valyqon-public-sources \
     -f ops/public_sources/compose.yaml run --rm --no-deps enqueue
   ```

   The `enqueue` runs only the explicitly enabled reviewed RU connectors;
   it makes **no upstream network fetch**. With overlays it can enqueue the
   six-source sequence, but never the disabled research adapters. The long-running Worker performs
   the actual bounded, first-party fetch and fenced durable SQL write.

4. Confirm job `succeeded` from the exact job ID printed by enqueue:
   `docker compose ... exec -T guest-sources python -m app.sources.enqueue --status <UUID>`
   Require genuine first-party original IDs, official host, nonzero accepted
   rows, verified persisted rows, no fixture, no hand-inserted SQL, no
   experimental account or email/Telegram send. Do not infer success from
   `docker ps` or from an empty market chart.
5. From the **isolated** guest API container (not the production container),
   run `python -m app.sources.isolated_runtime_audit` via
   `docker compose exec -T guest-sources` with the exact same Compose overlays.
   This module is included by the existing `Dockerfile` (`COPY app /app/app`);
   **`python -m scripts.verify_*` is not included in the built image**.
   The audit uses SQLite URI `mode=ro`, validates no outbound notifications,
   and emits only the six keys, per-source enabled flags, recent stored row
   counts, future-deadline preview counts and most recent durable Worker
   state/accepted count. No originals, buyer IDs, account data or secrets print.
   Its `PASS_READONLY` proves no publisher connection or public reverse proxy.
   The operator must additionally prove a fresh official publisher response,
   a real successful leased Worker job and a matching public HTTPS preview.
   Empty current tender results are **not** a release pass, even if the adapter
   registered or an old SQL row remains.
6. Test via a trusted Docker-network client or a *temporary private* test
   tunnel: GET `/api/v1/public/opportunities?q=...`, GET public market
   pulse and market intelligence, and the exact authenticated controls.
   **Do not permit the isolated source service to provide tenant routes**.
   Ensure only title, price, currency and deadline are returned to guests
   and never buyer, original source, external identity, documents, URLs or
   user/account data.
7. If official original, Worker receipt, freshness, isolated guest HTTP,
   exact reviewed commit, backup, Caddy config and rollback **all** pass,
   create a Caddy candidate by preserving every existing TLS, header,
   observability, AI help and ordinary API route. Add exact GET path
   matchers for:
   - `/api/v1/public/opportunities`
   - `/api/v1/public/market-pulse`
   - `/api/v1/public/market-intelligence`

   They alone reverse proxy to `guest-sources:8101` on
   `tenderlens-vps_edge`. Keep `/api/v1/public/help/ask` on
   `guest-ai:8100`, and **all other routes** on `api:8000`.

   Inspect the real effective Caddy route ordering; the site may already
   have other `handle`/matchers. **Do not paste a sample Caddyfile over it**.
   Validate candidate with the *live Caddy version* and then do an authorized
   Caddy-only reload. Never recreate the API or touch the production volume.

8. Outside HTTPS test live first-party preview, redaction, no-cache, Cyrillic
   search, market aggregates, empty search, user login/register, product AI
   Russian/English, old `/health`, source deny gates and all site pages.
   Compare Caddy and main API container IDs/hashes to pre-cutover. If any
   regression or empty/outdated results, restore the exact Caddyfile and
   reload, then stop the isolated source services if required.

## Optional continuous ingestion

Only after a live source is proven, explicitly start the separate
`verified-scheduler` profile. Scheduler has `network_mode:none` and
**only enqueues** the two explicitly approved jobs once per UTC hour each with durable same-hour
idempotency; the isolated Worker fetches the actual public source. It does
not send email, Telegram, customer reminders or paid source details.

```sh
docker compose --profile verified-scheduler -p valyqon-public-sources \
  -f ops/public_sources/compose.yaml up -d --no-deps scheduler
```

For additional source integration, make a separate reviewed patch for each:
strict domain allowlist, live original details, bounded job, isolated SQL,
dedup, active deadline filtering, guest projection and full CI.

## Rollback

Restore the byte-identical previous effective Caddy configuration and reload
Caddy only. Verify original source endpoints and functioning guest AI. Stop
`valyqon-public-sources` if needed, **without deleting volumes**. Keep the
old production API/SQLite intact. Monitor storage and source errors; the
isolated source volume does not confer a paid entitlement to source details.

## Six-source overlay promotion order

The overlay composition must always follow the staged prefix; never enable a
later source while omitting an earlier one:

```sh
docker compose -p valyqon-public-sources \
  -f ops/public_sources/compose.yaml \
  -f ops/public_sources/compose.south-ural.yaml \
  -f ops/public_sources/compose.kavkaz-rf.yaml \
  -f ops/public_sources/compose.lenobl.yaml \
  -f ops/public_sources/compose.samara-list.yaml \
  config --quiet
```

This command **only validates Compose** and does not deploy. The operator
must first inspect which overlay prefix actually runs on the VPS, preserve
the old isolated image, snapshot the isolated SQLite database using the
SQLite backup API, and verify that public Caddy already has the intended
separate guest-route handlers. Then opt in only the next missing source,
confirm fresh official originals (Samara: official list entries only),
bounded Worker `succeeded`, nonzero accepted/inserted records, future
deadline, and the isolated audit plus actual external HTTPS search.
If any step fails, restore the previously working Compose/image without
overwriting Caddy, production API, accounts or data. Start the
`verified-scheduler` only after every enabled source is independently
accepted. A nightly GitHub live test cannot substitute for this VPS receipt.

**Release claim:** Six isolated source overlays are implemented, but this
documentation and CI do **not** install any overlay or change public Caddy.
A passing source test is not proof a live website receives that source.
