# VALYQON staged public stack — private PostgreSQL Worker, opt-in Telegram

**This is not a deployed or approved commercial service.** This dedicated
Compose overlay is based on PR #297's reviewed release candidate. It does not
change the running site, secrets, user data or current production containers.

## Why this overlay exists

The default public Compose starts the API, Caddy and a Telegram polling
process, but contains **no durable connector Worker**. A real source can be
implemented and its job queued while nobody consumes it, leading to a polished
website without fresh SQL results. At the same time, automatically starting an
unconfigured Telegram bot can conflict with another process polling the same
token.

With the additional `compose.public-operator.yaml`:

- **Default profile:** only private FastAPI and the HTTPS Caddy edge. No bot,
  connector Worker or automatic procurement polling.
- **`authorized-telegram` profile:** start the Telegram bot **without
  background notifications** until a separately consented Bot API receipt
  and production delivery review are complete.
- **`reviewed-source-worker` profile:** run `app.jobs.worker --connectors`
  against an explicitly supplied external PostgreSQL DSN. It has no host
  ports. It does not automatically enqueue source jobs, enable any adapter,
  notify customers, accept payments or expose the SQLite demo database.

All three application processes require PostgreSQL through the separately
reviewed `compose.postgresql.example.yaml` override.

## Non-destructive configuration inspection

Supply only locally controlled operator configuration. Never commit an
`.env`, secret, decrypted backup or test customer database. The following is
a static inspection only and does **not** start a container:

```sh
docker compose \
  -f compose.public.yaml \
  -f compose.postgresql.example.yaml \
  -f compose.public-operator.yaml \
  config --services
```

It must list only `api` and `caddy` when no profile is enabled. The CI
checks both opt-in profiles, that all application processes use PostgreSQL,
that the Worker command is strict, and that only Caddy exposes ports.

## Later authorized operations — not performed by this PR

1. Operator selects a real HTTPS domain and independently controlled host.
2. Operator provisions PostgreSQL 16 with isolated privileges and backup/
   restore evidence; a database migration requires separate approval.
3. The actual hosted HTTPS route is tested with the release preflight;
   historical login redirects or unhealthy HTTP 200 must fail.
4. Only after reviewed source flags, source-specific live evidence and
   operational clearance can the operator enable `reviewed-source-worker`.
5. Durable jobs are queued deliberately through the existing operator
   command `python -m app.sources.enqueue --source <approved-source-id>`
   in the matching environment. This overlay **does not schedule them**.
6. Real customer alerts require consent, a dedicated test bot/chat, actual
   Telegram/email provider receipt, no duplicate claims and monitoring
   configuration review. The overlay cannot certify or authorize this.
7. Real customer billing requires a real merchant, signed webhook handling,
   entitlements, legal seller, privacy/consent, refunds and a supported
   subscription lifecycle. No billing is activated by this overlay.

Do not run public deployment, database cutover, production bot polling or
source jobs merely because GitHub CI is green. A green Compose test proves
configuration shape only and **never** proves production recovery, live tenders,
external alerts, payment acceptance or commercial readiness.
