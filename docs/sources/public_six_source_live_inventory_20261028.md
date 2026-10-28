# VALYQON: verify the six isolated Russian public sources on the actual VPS

**Read-only diagnostic, not a deployment.** A green GitHub workflow or source
overlay in `main` does not prove a corresponding Worker is serving
`https://valyqon.duckdns.org`. The main application's public source directory
also does **not** reflect the isolated worker's configured list.

## Public remote verification, no host access required

Run the hosted PR #354 GitHub Action `VALYQON live public source route audit (read only)`.
It checks only four fixed HTTPS GET routes:
- `/api/v1/public/opportunities`
- `/api/v1/public/market-pulse`
- `/api/v1/public/market-intelligence`
- `/public/source-directory.json`

It reports counts and main API enabled keys, but guest results intentionally
hide origin/source identifiers. The main API runtime flags are not evidence of
which isolated sources are actually on.

## Source-by-source read-only VPS verification

From the **trusted VPS only**, inspect the `valyqon-public-sources`
project; NEVER run this against `tenderlens-vps` or its SQLite volume.

If the six-source overlay is already deployed, run only this diagnostic:

```sh
docker compose -p valyqon-public-sources \
  -f ops/public_sources/compose.yaml \
  -f ops/public_sources/compose.south-ural.yaml \
  -f ops/public_sources/compose.kavkaz-rf.yaml \
  -f ops/public_sources/compose.lenobl.yaml \
  -f ops/public_sources/compose.samara-list.yaml \
  exec -T guest-sources python -m app.sources.isolated_public_inventory
```

The module is installed **inside** the Docker image because it belongs to
`app/sources`. Unlike `scripts/*.py`, it is copied by the repository
Dockerfile. If the deployed image predates the audit module,
`ModuleNotFoundError` means this diagnostic has not been deployed; it does
NOT mean the underlying sources are missing or broken.

The audit requires the exact isolated database URL and explicit operator
flag; connects to SQLite in `mode=ro` with `PRAGMA query_only=ON` and
never creates tables, enqueues jobs, fetches external data, or sends alerts.
It prints only six source IDs, enabled flags and bounded row counts:

- `MIKROTON_TENDER_ENABLED`
- `STAN_COMMERCIAL_PUBLIC_ENABLED`
- `SOUTH_URAL_PUBLIC_ENABLED`
- `KAVKAZ_RF_FIRSTPARTY_ENABLED`
- `LENOBL_SMALL_PUBLIC_ENABLED`
- `RU_SAMARA_PUBLIC_LIST_ENABLED`

A nonzero recent-unexpired count is a **stored preview candidate**, not proof
of a genuine upstream response, fenced Worker receipt, live Caddy route, or
customer delivery. Those still require official first-party Worker evidence,
external guest HTTPS verification and a checked real notice identity.

## Safe promotion boundary

The six source overlays were merged into `main` in #337, #339, #343,
#344 and #352. These only stage opt-in functionality; they do not
automatically update the deployed VPS image or Caddy routing. Samara is
**official public list-only**, and individual deep details are unverified.
Do not enable any blocked Chechnya, Ingushetia, GPB, Roseltorg, or TEK-Torg
PR as a substitute.

Before activating additional sources: inspect the live network and service
configuration read-only, obtain verified recent first-party notice and job
receipts, preserve existing Caddy/production backup and rollback, validate
the exact deployed image SHA, and keep guest redaction and AI routes intact.
Never rewrite the production Caddyfile with a generic example.

**Production changes performed by this audit: NONE.**
