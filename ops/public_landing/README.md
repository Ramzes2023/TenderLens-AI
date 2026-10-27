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


## One owner-side read-only topology command

GitHub cannot access the operator's local SSH private key. Run only from
the already available `VALYQON-PUBLIC-DIAG-20261026` Windows checkout:

```powershell
$p = "$HOME\VALYQON-PUBLIC-DIAG-20261026"
$k = "$HOME\.ssh\tenderlens_vps_ed25519"
git -C $p pull --ff-only origin fix/public-vps-local-preflight-20261026
if ($LASTEXITCODE -ne 0) { throw "Git fast-forward failed; no server action" }
Push-Location $p
try {
    py -3.12 -B -m scripts.valyqon_public_caddy_topology `
      --ssh-host 63.189.75.15 --ssh-key $k
    Write-Host "TOPOLOGY_EXIT_CODE=$LASTEXITCODE"
} finally {
    Pop-Location
}
```

This checks six short pinned-SSH commands without reading or uploading local
key bytes, private source, server configuration contents, customer records,
secrets, SQL data or backups. Only finite status labels are printed; no
Docker services are changed. The return code is 0 only if the existing Caddy
looks structurally compatible with the reviewed Compose overlay. **Even
a topology PASS is not deployment approval or backup/rollback proof**.

A BLOCKED result does not mean the VPS is offline; it may be a different
legacy Compose root, another Caddy service, non-Docker reverse proxy or
current shell permissions. Do not blindly use the overlay until the running
proxy is identified and safe rollback accepted. 
