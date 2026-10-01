# TenderLens AI — 5–10 minute demo

This script is designed for a portfolio interview or screen-share demo.

## 1. Show automated quality checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Explain: tests cover configuration, Telegram routing, PDF limits, LLM boundaries, scoring, database/dedup, RAG, monitoring, API and deployment assets without calling live external APIs.

## 2. Start the containerized API

```powershell
docker compose up -d
docker compose ps
curl.exe http://127.0.0.1:8000/health
```

Expected: container status `healthy` and `status: ok`. On a fresh Docker volume, if RAG reports unavailable, initialize the model cache once:

```powershell
docker compose exec -e OUTBOUND_PROXY_URL= api python -m app.rag.health
docker compose restart api
```

Then run the smoke checker:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_api.py
```

## 3. Open Swagger

Open `http://127.0.0.1:8000/docs`.

Show:

- `/health`
- `/api/v1/tenders`
- `/api/v1/analysis/pdf`
- `/api/v1/scoring/evaluate`
- `/api/v1/rag/ask`
- monitoring endpoints

Explain that the HTTP transport calls the same domain services as Telegram rather than reimplementing logic.

## 4. Show the Telegram document workflow

Run the bot locally if it is not already running:

```powershell
.\.venv\Scripts\python.exe -m app.bot
```

Send `examples/sample_tender.pdf` to the bot.

Point out the pipeline:

1. local PDF parsing;
2. strict structured AI extraction;
3. deterministic profile fit score;
4. SQLite persistence and SHA-256 dedup;
5. RAG index creation.

Send the same PDF again and show that exact duplicate analysis is reused instead of spending another full LLM request.

## 5. Demonstrate semantic RAG

Ask a paraphrased question rather than copying the PDF wording:

```text
/ask Что произойдет, если поставщик задержит доставку?
```

Explain: the multilingual embedding model retrieves semantically related chunks from Qdrant, and the answer cites the retrieved page.

## 6. Demonstrate live EIS monitoring

```text
/monitor_status
/tenders
```

If `MONITORING_ENABLED=true`:

```text
/monitor_on
```

Explain that RSS is intentionally only a discovery/pre-filter layer. A discovered notice is not treated as authoritative full tender analysis until documents are processed.

## 7. Close with engineering trade-offs

Mention three choices:

- **Deterministic scoring outside the LLM** for reproducibility.
- **Owner/document filters in RAG** to avoid cross-document retrieval.
- **Single-node SQLite/Qdrant local deployment** for a reliable portfolio MVP; production scale would move both to server-backed services.

Then show `SECURITY.md` and the CI workflow to demonstrate that limitations and operational risks are documented rather than hidden.
