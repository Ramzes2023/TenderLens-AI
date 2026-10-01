# Deployment guide

## Supported portfolio deployment

TenderLens v1.0.0 ships a single-node Docker Compose deployment for the FastAPI service.

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

The API is bound to `127.0.0.1:8000` by default.

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

- `/app/data/tenderlens.db`
- `/app/data/qdrant`
- `/app/data/fastembed_cache`

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
```

Do not paste logs publicly if you have enabled additional verbose vendor diagnostics or added custom code that logs request data.

## API key

For anything beyond localhost demo use, set a strong `TENDERLENS_API_KEY` and send it as `X-API-Key` to `/api/v1/*`.

This is still not full production authentication. Public exposure also needs HTTPS, identity/authorization, rate limiting, monitoring and hardened secret management.

## Proxy note

A host proxy at `127.0.0.1` is not automatically the same address from inside a container. Configure container-reachable networking deliberately. For the FastEmbed one-time health command, `-e OUTBOUND_PROXY_URL=` can force direct access when appropriate.

## Scaling limitation

Do not run several application replicas against the same Qdrant local directory. For multiple workers/replicas migrate to PostgreSQL and Qdrant server/Cloud first.
