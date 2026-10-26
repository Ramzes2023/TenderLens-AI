# VALYQON staged public stack — private PostgreSQL Worker, opt-in Telegram

**This is not a deployed or approved commercial service.** This dedicated
Compose overlay is based on current `main`, which already contains the verified-bot public profile and fail-closed source switches. It does not
change the running site, secrets, user data or current production containers.

## Why this overlay exists

The default public Compose already starts only API and Caddy, but contains **no durable connector Worker**. A real source can be
implemented and its job queued while nobody consumes it, leading to a polished
website without fresh SQL results. At the same time, a Telegram bot must remain strictly opt-in: an unexpected second polling process can conflict with an existing token.

With the additional `compose.public-operator.yaml`:

- **Default profile:** only private FastAPI and the HTTPS Caddy edge. No bot,
  connector Worker or automatic procurement polling.
- **`verified-bot` profile:** start the Telegram bot **without
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

## Public release truth as of 26 October 2026

This overlay **does not launch the website**. Default production runs only `api` and `caddy`, with experimental Russian sources, deadline alerts, AI and paid details fail-closed. No legal operator, registered seller, reviewed personal-data consent, verified public canonical HTTPS domain, external deliverable SMTP or merchant subscription entitlement was supplied in this PR. The current `compose.public.yaml` still has SQLite as the base; the operator must include `compose.postgresql.example.yaml` to use a reviewed external PostgreSQL 16 instance.

Only a separate approved operator rollout can activate the optional connector profile **after** specific real-original-source, Worker→DB→authorized user, delivery and backup acceptance. The overlay and CI explicitly deny unreviewed source flags inherited from `.env`, including on the Worker. Adding an opt-in Worker is **not** a substitute for obtaining user consent, running a source job or proving search results.

A read-only audit of the exact running image and HTTPS health should precede any changes to the existing VPS. Do not overwrite its `.env`, `docker-compose` project or persistent volumes from these instructions.
