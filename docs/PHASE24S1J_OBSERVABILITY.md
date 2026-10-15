# Phase 24S.1J ? Observability

## Audit and scope

| Boundary | Existing behavior | Added visibility |
| --- | --- | --- |
| API | Capability-only `/health`; independently composed optional services | Pure ASGI request duration/outcome and generated response correlation ID |
| Durable jobs | Relational leases, fenced completion, bounded persisted failure codes | Enqueue, claim (including empty), heartbeat, completion/failure and execution diagnostics |
| Quotas | Transactional admissions, daily/monthly/outstanding budgets | Admission outcomes including denied; no tenant keys or per-tenant labels |
| AI gateway | Concurrency cap, timeout, bounded transport retries, safe error translation | Generation duration/error category, attempt and retry counts |
| RAG | Scoped retrieval, bounded chunks/context, durable ingestion | Index, retrieval and answer outcomes/durations; ingestion also covered by job execution |
| Connectors | Approved routing, bounded fetch and record counts, safe worker errors | Sync duration and retryable/permanent outcomes, queue state aggregates |
| Existing telemetry | Local capability health, source health, cache status, manual live health commands | Trusted local operator snapshot; existing health contracts remain intact |

Manual `app.llm.health`, `app.rag.health` and source health commands are existing live diagnostics, not used by this phase or its operator command. Existing source-specific health and persisted job results retain their existing authorization boundaries. Monitoring matching is unchanged. No Phase 24S.2 work, external calls, deployment or schema migration is needed.

## Enablement

Both optional facilities are disabled by default. Set `VALYQON_OBSERVABILITY_LOGS=1` and/or `VALYQON_OBSERVABILITY_METRICS=1` in the process environment **before process startup/import**, then restart. Other values disable the facility. This intentionally does not load a `.env` file independently. Existing deployment environment injection may supply these flags.

Logs use the `valyqon.observability` logger at INFO. Operators must configure an INFO sink using their existing logging setup; this feature neither installs handlers nor changes root/third-party logger policy. A failing log sink is ignored. Each event is a JSON object with only event, outcome, duration_ms, and an optional generated correlation_id. No arbitrary metadata interface is provided.

Metrics live in a locked, process-local registry with at most `len(OPERATIONS) * len(OUTCOMES)` series. Each fixed operation/outcome pair has count, duration sum and maximum. No tenant, account, company, job, document, source URL, provider/model, path, prompt, response, credential, exception text or traceback becomes a label or log field. Correlation IDs are log fields only. No exporter, network listener, collector thread or telemetry database exists. Counters reset at process restart; API and worker processes have independent registries. Attempt/retry counters are events, not completed-generation counts or billing measurements. Quota admission measurements describe the boundary invocation, not a guarantee of a later transaction commit.

HTTP responses add `X-Correlation-ID`, including application error responses started by the ASGI app. IDs are random 32-character hex values generated locally. Incoming correlation headers are ignored. Context is isolated across requests and reset on completion/error/cancellation; async-to-thread RAG work inherits context. Each worker `run_once` creates a separate execution scope; request IDs are deliberately not persisted in job payloads or schema. Heartbeat threads have no inherited correlation context. Unhandled errors synthesized outside this middleware by the framework may lack the header.

## Operator use

Run `python -m app.observability.health` against the configured database. It executes aggregate SELECT queries only, does not migrate or claim jobs, prints safe JSON, and exits 0 on successful queries or 1 with fixed unavailable statuses on failure. Queue output contains counts for fixed states, oldest queued age, expired leases, active retried jobs and fixed persisted failure-code counts. No IDs, payloads, results, tenant breakdowns or database connection strings are printed. Age includes scheduled/delayed jobs. Expired leases are diagnostic; normal claim recovery remains responsible for recovery. Queries require the existing durable job schema and can scan large historical tables: run on demand, not per request.

Within a trusted running process, `app.observability.health.runtime_snapshot(runtime)` returns sanitized capability statuses, aggregate queue diagnostics and that process's metric snapshot. The API also exposes the registry to trusted Python operators as `app.state.telemetry.snapshot()`. There is no public metrics/diagnostics endpoint or new authorization surface. The standalone CLI cannot read another process's metrics. Local capability readiness never proves external provider connectivity; snapshots explicitly report `not_probed`. Use existing worker pool `alive_count`/`worker_count` for embedded worker liveness; queue counts alone cannot prove a separate worker is alive.

## Offline validation

`tests/test_observability.py` covers disabled behavior, closed vocabulary, secret exclusion, concurrent counters, sink failure, correlation nesting/isolation, ASGI streaming/header replacement, cancellation and read-only aggregate queue queries using temporary SQLite storage. Focused regressions cover API, durable jobs, quotas, AI gateway/cache/failover, RAG/ingestion and connector workers. No real provider calls are required.
