# VALYQON static public landing — isolated release candidate

This is a **limited, non-commercial public homepage**, not a SaaS product release,
not an authenticated user-facing API upgrade, and not a migration. It is
prepared in PR #318 for the **existing** Caddy+API Compose deployment only.
Committing/merging these files does not deploy anything.

## Why this track

The old VPS currently redirects GET / to /login. The reviewed application
contains a better premium homepage but starting a different API image against
the existing SQLite volume may modify its schema. This track changes **only
Caddy routing at the exact root path** and serves two static files.
It does not launch another API process, worker, Telegram bot, Mailpit,
PostgreSQL migration or touch the SQLite data volume.

Files:
- `site/index.html` — truthful marketing-only preview without fake tenders,
  statistics, subscription/payment promises, registration forms or JS.
- `site/valyqon-public-landing.css` — responsive stylesheet, no external CDN.
- `Caddyfile` — only / and /valyqon-public-landing.css served locally; every
  other route proxied to the **existing** api:8000.
- `compose.static.yaml` — a reviewed, read-only Caddy mount overlay;
  no extra public ports, DB mounts, Docker images, build, bot or workers.

## Hard preconditions; **not yet verified**

1. Operator verifies the production hostname and that its running **Caddy**
   belongs to the exact Compose project used in this repository.
   A legacy `phase20-valyqon` deployment may have different service names
   or its own Caddyfile. **Never run the overlay against an unverified stack.**
2. Verify 80/443 exposure, original TLS, existing `/login` and `/health`,
   running container image identity and Caddy's current mounted config.
3. Record a copy of the **current effective Caddy configuration** and the
   exact pre-change service container/Compose configuration as a rollback
   artifact in the secured server release directory, not in git or chat.
4. Review the static wording, public hostname and basic business information.
   Static links only to existing /login. Public registration, paid access, AI,
   alerts, SMS/email, Telegram, recurring source collection stay OFF.
5. Stage on a separate test host/port. Confirm Caddy configuration parses,
   homepage CSS 200, CSP and no redirect at /, and that /login, /health and
   /api/v1/auth/me retain old behavior.
6. Operator explicitly authorizes **only public static files and reviewed
   Caddy routing**, with source/destination and a rollback plan. Do not
   transfer any other repository files, private application source, .env,
   production DB, backups, SSH private keys or recovery material.

## Safe offline review only

```sh
python -m pytest -q tests/test_valyqon_public_static_landing.py
```

For syntax check in an isolated environment (no production network/volumes):

```sh
docker run --rm \
  -v "$PWD/ops/public_landing/Caddyfile:/etc/caddy/Caddyfile:ro" \
  -e TENDERLENS_DOMAIN=example.test -e ACME_EMAIL=release@example.test \
  caddy:2.11.6-alpine caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile
```

Production change is **not authorized by this runbook**. A future strictly
operator-controlled limited release, **only after the conditions above pass**,
may mount these public static files and atomically reload/recreate **only**
the already-running Caddy service, without rebuilding/upgrading the API or
touching any customer database or volume.

Post-change acceptance must independently verify trusted TLS, GET / 200
with the static distinctive title and no login redirect, stylesheet HTTP 200,
CSP, /login and /health continuing to work, /api/v1/auth/me correctly 401
without credentials, no unintended exposure of SQLite/PG/Mailpit and ready
rollback. Any failure → immediately revert the Caddy overlay using the
captured previous config. Never use `docker compose down -v`.

**Commerce, sign-up, payment, AI, source-to-user delivery and PostgreSQL
cutover are still BLOCKED** independently of a successful static landing.
