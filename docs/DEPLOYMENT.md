# Deployment guide

## Supported portfolio deployment

VALYQON AI ships a single-node Docker Compose deployment with two services: `api` (FastAPI) and `bot` (Telegram polling + EIS monitoring).

Requirements:

- Docker Engine / Docker Desktop
- on Windows: WSL2 backend supported by Docker Desktop
- `.env` created from `.env.example`

## Build and start

```powershell
docker compose build
docker compose up -d
docker compose ps
```

The API is bound to `127.0.0.1:8000` by default. The `bot` service exposes no port and runs Telegram long polling in the background.

```powershell
curl.exe http://127.0.0.1:8000/health
```

Swagger: `http://127.0.0.1:8000/docs`

## First-time semantic model cache

FastEmbed downloads the multilingual ONNX model on first use. The cache lives in the persistent `tenderlens_data` volume.

If `/health` reports `rag: unavailable` on a brand-new volume:

```powershell
docker compose exec -e OUTBOUND_PROXY_URL= api python -m app.rag.health
docker compose restart api
```

Then verify `/health` again.

## Persistence

The named volume stores:

- `/app/data/tenderlens.db` (shared SQLite history/monitoring state)
- `/app/data/qdrant` (API local RAG index)
- `/app/data/qdrant-bot` (Telegram bot local RAG index)
- `/app/data/fastembed_cache` (shared embedding model cache)

Inspect volumes:

```powershell
docker volume ls
```

Stop containers without deleting state:

```powershell
docker compose down
```

Delete the named volume only when you intentionally want to erase local VALYQON AI state:

```powershell
docker compose down -v
```

## Logs

```powershell
docker compose logs -f api
docker compose logs -f bot
```

Do not paste logs publicly if you have enabled additional verbose vendor diagnostics or added custom code that logs request data.

## Authentication and API key

Browser users authenticate with the HttpOnly Web session cookie.

Shared organization APIs require session identity plus organization membership
and role authorization. `TENDERLENS_API_KEY` remains available only for
supported legacy/personal integration paths and is not organization identity.

The default deployment remains localhost-first. Public exposure additionally
needs HTTPS/reverse-proxy hardening, distributed rate limiting, monitoring,
structured audit logging, retention/backups and hardened secret management.

## Proxy note

A host proxy at `127.0.0.1` is not the same address from inside a container. Compose therefore overrides the host `OUTBOUND_PROXY_URL` / `TELEGRAM_PROXY_URL` with Docker-specific variables. Leave `DOCKER_OUTBOUND_PROXY_URL` and `DOCKER_TELEGRAM_PROXY_URL` empty for normal container networking, or set them to a proxy URL that is actually reachable from the container. For the FastEmbed one-time health command, `-e OUTBOUND_PROXY_URL=` can force direct access when appropriate.

## Scaling limitation

Qdrant local mode is file-backed. API and bot therefore use separate local Qdrant directories while sharing SQLite and the model cache. Do not scale either service to multiple replicas with local Qdrant/SQLite; migrate to PostgreSQL and Qdrant server/Cloud first.

## Public HTTPS edge

`compose.public.yaml` adds Caddy TLS termination, HTTP-to-HTTPS redirect, security
headers and explicit trusted-proxy networking. Only Caddy publishes ports 80/443;
the API is internal. Public settings are documented in `.env.public.example`.
Existing production keeps its current runtime env, project name and volume.
The branding change requires no data or infrastructure migration; see
[compatibility](BRANDING_COMPATIBILITY.md). This guide does not authorize a deployment.

### Exact public Compose environment-file behavior

`.env.public.example` is **only a template**. Compose does not automatically load
a file named `.env.public`. Public edge variable interpolation requires an
explicit `--env-file .env.public`; the `api` service still separately requires
a secured `.env` through its `env_file` entry. Do not commit either file.

On a **dedicated authorized staging VPS only**, after provisioning the real
DNS hostname, ACME contact and a dedicated non-customer state volume:

```sh
# Provision .env and .env.public through the operator's secret channel first.
docker compose --env-file .env.public -f compose.public.yaml config --quiet
# Review every rendered setting privately. Do not paste secret-bearing
# 'docker compose config' output into GitHub logs or public chat.
docker compose --env-file .env.public -f compose.public.yaml up -d --build api caddy
python -B scripts/verify_public_https.py --url https://YOUR-REAL-DOMAIN
```

This is **not** an instruction to run the command against the existing VPS or
production data before independent acceptance. In particular, do not run
`down -v`, do not start a second Telegram polling process and do not expose
PostgreSQL, Mailpit, the bot or the API directly to the public Internet.
The bot is intentionally absent from the initial HTTPS-only staging startup.
Public analytics operate in **real-data mode** in the release candidate;
without verified Worker storage they must show an empty/unavailable state, not
fictional notice counts. Paid source details stay locked pending entitlements.
See [current release blockers](PUBLIC_LAUNCH_READINESS_20261025.md).

Single-node storage, process-local throttling and operational backup/retention
requirements still apply. HTTPS does not imply high availability or certification.
