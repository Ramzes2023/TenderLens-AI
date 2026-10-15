"""Offline privacy, bounded cardinality, correlation, and operator diagnostics checks."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from unittest.mock import patch

import pytest

import app.observability as obs
from app.observability.health import queue_snapshot
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import JobRepository, JobScope


def test_disabled_and_closed_vocabulary(caplog):
    with caplog.at_level(logging.INFO):
        disabled = obs.Telemetry()
        disabled.record("api.request")
        assert disabled.snapshot() == [] and not caplog.records
        enabled = obs.Telemetry(logs=True, metrics=True)
        enabled.record("secret-tenant-path", "secret")
        assert enabled.snapshot() == [] and not caplog.records
        enabled.record("api.request", seconds=float("nan"))
        assert json.loads(caplog.records[-1].message) == {"event": "api.request", "outcome": "success", "duration_ms": 0}


def test_concurrent_metrics_and_private_exceptions(caplog):
    telemetry = obs.Telemetry(logs=True, metrics=True)
    @obs.observe("rag.retrieve")
    def failure(secret):
        raise ValueError(secret)
    with patch.object(obs, "telemetry", telemetry), caplog.at_level(logging.INFO):
        with pytest.raises(ValueError):
            failure("PRIVATE PROMPT TOKEN TENANT")
        assert "PRIVATE" not in caplog.text
        with ThreadPoolExecutor(4) as pool:
            list(pool.map(lambda _: telemetry.record("ai.attempt"), range(200)))
    rows = telemetry.snapshot()
    assert next(row for row in rows if row["operation"] == "ai.attempt")["count"] == 200
    assert len(rows) == 2


def test_sink_failure_and_correlation_reset():
    with obs.correlation() as first:
        with obs.correlation() as second:
            assert first != second and len(second) == 32
        assert obs._correlation.get() == first
    assert obs._correlation.get() is None
    with patch.object(logging.Logger, "info", side_effect=RuntimeError("secret")):
        obs.Telemetry(logs=True).record("ai.generate")


def test_asgi_streaming_headers_and_concurrent_context():
    telemetry = obs.Telemetry(metrics=True)
    async def app(scope, receive, send):
        before = obs._correlation.get()
        await asyncio.sleep(0)
        assert before == obs._correlation.get()
        await send({"type": "http.response.start", "status": 200, "headers": [(b"x-correlation-id", b"private")]})
        await send({"type": "http.response.body", "body": b"ok"})
    async def request():
        messages = []
        async def send(message):
            messages.append(message)
        await obs.RequestDiagnostics(app)({"type": "http", "path": "/private/tenant", "headers": [(b"x-correlation-id", b"secret")]}, None, send)
        assert obs._correlation.get() is None
        assert messages[1]["body"] == b"ok"
        return messages[0]["headers"][0][1]
    async def run():
        with patch.object(obs, "telemetry", telemetry):
            values = await asyncio.gather(request(), request())
        assert len(set(values)) == 2 and all(len(value) == 32 for value in values)
    asyncio.run(run())
    assert telemetry.snapshot()[0]["count"] == 2


def test_async_cancellation_is_preserved():
    telemetry = obs.Telemetry(metrics=True)
    @obs.observe("ai.generate")
    async def cancel():
        raise asyncio.CancelledError()
    with patch.object(obs, "telemetry", telemetry), pytest.raises(asyncio.CancelledError):
        asyncio.run(cancel())
    assert telemetry.snapshot()[0]["outcome"] == "cancelled"


def test_queue_diagnostics_read_only_and_no_private_fields(tmp_path):
    database = Database(DatabaseSettings("", tmp_path / "jobs.db"))
    try:
        repository = JobRepository(database, clock=lambda: 1800000000)
        repository.initialize()
        job = repository.enqueue("fixture.work", {"secret": "private"}, scope=JobScope())
        result = queue_snapshot(database, 1800000010000000)
        assert result["states"]["queued"] == 1
        assert result["oldest_queued_seconds"] == 10
        assert result["expired_leases"] == 0
        assert "private" not in json.dumps(result) and job.id not in json.dumps(result)
        assert repository.get(job.id, scope=JobScope()).state == "queued"
        claim = repository.claim_next("worker-" + "a" * 32)
        assert repository.fail(job.id, claim.token, retryable=True)
        retried = queue_snapshot(database, 1800000010000000)
        assert retried["active_retried_jobs"] == 1
        assert retried["failure_codes"]["handler_error"] == 1
    finally:
        database.close()


def test_worker_correlation_and_failure_outcome(tmp_path, caplog):
    from app.jobs import HandlerRegistry
    from app.jobs.worker import Worker, RetryableJobError
    database = Database(DatabaseSettings("", tmp_path / "worker.db"))
    telemetry = obs.Telemetry(logs=True, metrics=True)
    seen = []
    def handler(context, payload):
        seen.append(obs._correlation.get())
        raise RetryableJobError("PRIVATE JOB PAYLOAD")
    try:
        repository = JobRepository(database)
        repository.initialize()
        repository.enqueue("fixture.work", {"private": "secret"}, scope=JobScope())
        registry = HandlerRegistry()
        registry.register("fixture.work", handler)
        with patch.object(obs, "telemetry", telemetry), patch("app.jobs.worker.telemetry", telemetry), caplog.at_level(logging.INFO):
            assert Worker(repository, registry).run_once()
        assert len(seen[0]) == 32 and obs._correlation.get() is None
        assert "PRIVATE" not in caplog.text and "secret" not in caplog.text
        executions = [row for row in telemetry.snapshot() if row["operation"] == "job.execute"]
        assert len(executions) == 1 and executions[0]["outcome"] == "retryable"
        assert all(json.loads(record.message).get("correlation_id") == seen[0] for record in caplog.records)
    finally:
        database.close()


def test_ai_error_categories_exclude_provider_messages():
    from app.llm.base import LLMTimeoutError, LLMAuthenticationError, LLMRateLimited
    telemetry = obs.Telemetry(metrics=True)
    for kind, expected in ((LLMTimeoutError, "timeout"), (LLMAuthenticationError, "authentication"), (LLMRateLimited, "rate_limited")):
        @obs.observe("ai.generate")
        async def fail():
            raise kind("provider credential and private request")
        with patch.object(obs, "telemetry", telemetry), pytest.raises(kind):
            asyncio.run(fail())
        assert expected in {row["outcome"] for row in telemetry.snapshot()}
    assert len(telemetry.snapshot()) == 3


def test_runtime_snapshot_sanitizes_component_status():
    from app.observability.health import runtime_snapshot
    class Runtime:
        database = None
        def component_status(self):
            return {"llm": "secret-provider-error", "database": "ready", "unknown-secret": "ready"}
    result = runtime_snapshot(Runtime())
    assert result["components"]["llm"] == "unavailable"
    assert result["queue"] == "unavailable"
    assert "secret" not in json.dumps(result)
