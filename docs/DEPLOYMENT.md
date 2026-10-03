# Deployment guide

## Supported portfolio deployment

TenderLens ships a single-node Docker Compose deployment with two services: `api` (FastAPI) and `bot` (Telegram polling + EIS monitoring).

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

Delete the named volume only when you intentionally want to erase local TenderLens state:

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
