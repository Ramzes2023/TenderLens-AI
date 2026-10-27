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

Current initial adapter: `mikroton_tender` ONLY. It represents a separate
commercial public procurement source, not EIS. Its documented public HTTPS API
has active and archived endpoints: https://tender.mt52.ru/api-docs .
**An official site showing no active tenders must lead to a blocked cutover,
not sample/demo records or re-labeled archived procurement.**

Other RU adapters are present in the main repository but are not enabled in
this release. Ingushetia, Chechnya, TEK-Torg, GPB, Fabrikant, Roseltorg,
Samara, Dagestan and CIS research PRs remain off until their own independent
first-party original, Worker, SQL, leak, dedup and source freshness gates
pass. Never enable them as a blanket group.

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

   The `enqueue` runs only the approved, enabled MikroTon connector; it
   makes **no upstream network fetch**. The long-running Worker performs
   the actual bounded, first-party fetch and fenced durable SQL write.

4. Confirm job `succeeded` from the exact job ID printed by enqueue:
   `docker compose ... exec -T guest-sources python -m app.sources.enqueue --status <UUID>`
   Require genuine first-party original IDs, official host, nonzero accepted
   rows, verified persisted rows, no fixture, no hand-inserted SQL, no
   experimental account or email/Telegram send. Do not infer success from
   `docker ps` or from an empty market chart.
5. In the **isolated** guest API's container run
   `python -m scripts.verify_isolated_public_source_release`. The gate
   requires a recently fetched MikroTon source identity, a public original
   URL, a future submission deadline, and at least one source preview.
   A successful gate reports `PUBLIC_SOURCE_PROMOTION=CANDIDATE_ONLY`,
   not permission to skip an independent official-source Worker receipt.
   If `BLOCKED_NO_FRESH_ORIGINALS`, do not promote this source; it may
   have only archived/closed procedures.
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
**only enqueues** the MikroTon job once per UTC hour with durable same-hour
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

**Release claim:** this PR provides source-to-public-site wiring for a
staged operator-controlled rollout. It does not itself change public Caddy,
and passing unit tests alone does NOT mean any live website received tenders.
