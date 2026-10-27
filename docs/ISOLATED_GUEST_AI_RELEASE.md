# VALYQON isolated guest AI — no production SQLite migration

**Status: SOURCE/STAGING CANDIDATE ONLY. NO production deployment.**

## Why use a separate service?

The current public website was observed using a legacy image
`tenderlens-ai:public-demo-821bd6b` on a five-file Compose project,
with a persistent SQLite data volume. It has no daily anonymous-model
budget and `VALYQON_PUBLIC_AI_ENABLED=false`. Replacing its main API
image risks applying migrations to the production SQLite database.

The alternative is a dedicated **product FAQ only** responder. It
reuses the reviewed guest route and 3/IP/10-minute + 48/process/day
rate policies but instantiates **no ApiRuntime, Database, repositories,
worker, migrations, cache, email, Telegram or tenant services**.
Its Compose file has **no volume, host port or main API/Caddy service**.
Do not include it in the existing five-file public Compose invocation.
The existing API and its SQLite volume should remain unchanged.

## Operator prerequisites and explicit approval

- Exact review/CI of the final source commit, plus read-only inspection
  of the *actual* deployed Caddyfile, Caddy container and its Docker
  network membership. Never assume current GitHub Caddyfile is live.
- Verify that the existing Caddy joins `tenderlens-vps_edge` and
  can resolve the `guest-ai` hostname there. If not, **STOP**.
- Securely provision a *separate*, private env file with only the
  guest service's required `GIGACHAT_CREDENTIALS`,
  `GIGACHAT_MODEL` and (if needed) `GIGACHAT_SCOPE`. Do not
  duplicate unrelated database, email, billing or Telegram secrets.
  Do not commit, post, print or transfer this file through GitHub.
- Set provider-side spend caps and monitor usage. The process budget
  resets on restart and does not span replicas; this deployment must
  stay at one worker and one instance. Add edge/provider controls
  before broad public traffic.
- Keep the already verified SQLite backup and Windows DPAPI copy, but
  note they do not cover **every file** in the production data volume.
  Independently inventory and rehearse backup/restore of the complete
  data volume before any production cutover.
- Prepare a Caddy configuration rollback before changing ANY routing.
  This procedure does not authorize production changes by itself.

## Isolated build/staging (does not touch public API)

Use a reviewed source checkout in a **separate** directory on the VPS.
Never switch the dirty/older `/opt/tenderlens` checkout or overwrite its
five Compose overrides. Run in the reviewed source directory only:

```bash
# Set these only within the trusted VPS shell.
export VALYQON_GUEST_AI_ENV_FILE=/private/secure/path/guest-ai.env
docker compose -p valyqon-guest-ai \
  -f compose.isolated-guest-ai.yaml config --services
docker compose -p valyqon-guest-ai \
  -f compose.isolated-guest-ai.yaml build guest-ai
docker compose -p valyqon-guest-ai \
  -f compose.isolated-guest-ai.yaml up -d --no-deps guest-ai
```

This builds and starts only an internal, network-attached AI service.
The `guest-ai` container must have **no persistent volume** and **no
published host port**. The new image's default SQLite configuration is
inert because the ASGI factory never constructs the full API runtime.

Check its internal health and then send **one** synthetic product-only
question from inside the container. Do not log the text answer, model
credentials, upstream error bodies or private customer information.
Require HTTP 200, nonblank `answer` and `scope=public_product_only`;
otherwise do not expose this service through Caddy.

## Deliberate exact-path HTTPS routing (review first)

Only after a real model answer in isolated staging, prepare a candidate
configuration derived from the **actual** running Caddyfile, replacing
only the old default application proxy handler with routing equivalent to:

```caddy
route {
    @public_ai path /api/v1/public/help/ask
    handle @public_ai {
        reverse_proxy guest-ai:8100
    }
    handle {
        reverse_proxy api:8000
    }
}
```

Preserve every original TLS, HTTP->HTTPS, security header, logging,
ACME and additional route directive outside this snippet. Keep the
fallback for all other endpoints. Verify Caddy's network connectivity,
validate/adapt the candidate with the existing Caddy binary, and
preserve a private byte-identical previous Caddyfile. Only then perform
an approved, **Caddy-only** reload; **do not recreate API or attach
the SQLite volume to the guest service**.

If the current Caddyfile does not have a single simple
`reverse_proxy api:8000` handler, STOP and review the actual
routing order; do not apply the example verbatim.

An external HTTPS probe must report one real 200 generated answer.
Also recheck homepage, login, guest search, status, security headers,
API health, and the Caddy error rate. A successful isolated local
reply **does not** prove public traffic is reaching the new service.

## Rollback

Restore the byte-identical previously validated Caddy configuration
and reload Caddy only. Recheck the original public endpoints. After
traffic is routed back to the old API, stop the standalone guest-AI
Compose project. The original `/opt/tenderlens` main API, its five
Compose descriptors and SQLite volume must be untouched throughout.

**Do not claim guest AI is live until the public 200 acceptance test
passes. Do not change paid entitlement, real tender source flags,
subscriber messaging or billing.**
