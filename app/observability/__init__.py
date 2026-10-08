"""Opt-in, process-local diagnostics with a closed telemetry vocabulary."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from inspect import iscoroutinefunction
import json
import logging
import os
import threading
import time
import uuid

OPERATIONS = frozenset({"api.request", "job.enqueue", "job.claim", "job.complete", "job.fail",
    "job.heartbeat", "job.execute", "quota.admit", "ai.generate", "ai.attempt", "ai.retry",
    "rag.index", "rag.retrieve", "rag.answer", "connector.sync"})
OUTCOMES = frozenset({"success", "error", "cancelled", "denied", "retryable", "permanent", "lease_lost", "empty", "timeout", "rate_limited", "authentication", "unavailable", "invalid"})
_correlation = ContextVar("valyqon_correlation", default=None)


@contextmanager
def correlation():
    # Always generated locally: client headers and job payloads are untrusted.
    value = uuid.uuid4().hex
    token = _correlation.set(value)
    try:
        yield value
    finally:
        _correlation.reset(token)


class Telemetry:
    def __init__(self, *, logs=False, metrics=False):
        self.logs, self.metrics = logs, metrics
        self._lock = threading.Lock()
        self._series = {}

    def record(self, operation, outcome="success", seconds=0):
        if operation not in OPERATIONS or outcome not in OUTCOMES:
            return
        # No arbitrary metadata, labels, IDs, error strings, or provider/model names.
        if type(seconds) not in (int, float) or not 0 <= seconds <= 86400:
            seconds = 0
        if self.metrics:
            with self._lock:
                row = self._series.setdefault((operation, outcome), [0, 0.0, 0.0])
                row[0] += 1
                row[1] += seconds
                row[2] = max(row[2], seconds)
        if self.logs:
            event = {"event": operation, "outcome": outcome, "duration_ms": round(seconds * 1000, 3)}
            value = _correlation.get()
            if value is not None:
                event["correlation_id"] = value
            try:
                logging.getLogger("valyqon.observability").info(json.dumps(event, separators=(",", ":")))
            except Exception:
                pass  # A broken optional sink cannot change application behavior.

    def snapshot(self):
        with self._lock:
            return [{"operation": op, "outcome": outcome, "count": row[0],
                     "duration_seconds_sum": row[1], "duration_seconds_max": row[2]}
                    for (op, outcome), row in sorted(self._series.items())]


# Explicit environment opt-in; no exporters, threads, storage or network at import.
telemetry = Telemetry(logs=os.environ.get("VALYQON_OBSERVABILITY_LOGS", "0") == "1",
                      metrics=os.environ.get("VALYQON_OBSERVABILITY_METRICS", "0") == "1")


def _outcome(error):
    from app.llm.base import (LLMTimeoutError, LLMRateLimited, LLMAuthenticationError,
                              LLMNetworkError, LLMProviderUnavailable, LLMInvalidRequest, LLMInvalidResponse)
    for kind, outcome in ((LLMTimeoutError, "timeout"), (LLMRateLimited, "rate_limited"),
                          (LLMAuthenticationError, "authentication"), (LLMNetworkError, "unavailable"),
                          (LLMProviderUnavailable, "unavailable"), (LLMInvalidRequest, "invalid"),
                          (LLMInvalidResponse, "invalid")):
        if isinstance(error, kind):
            return outcome
    from app.quotas.admission import QuotaExceeded
    from app.jobs.worker import RetryableJobError, PermanentJobError
    from app.jobs.models import LeaseLostError
    if isinstance(error, QuotaExceeded):
        return "denied"
    if isinstance(error, RetryableJobError):
        return "retryable"
    if isinstance(error, PermanentJobError):
        return "permanent"
    if isinstance(error, LeaseLostError):
        return "lease_lost"
    return "error"


def observe(operation):
    if operation not in OPERATIONS:
        raise ValueError("Unknown telemetry operation.")
    def decorate(function):
        @wraps(function)
        async def asynchronous(*args, **kwargs):
            started, outcome = time.monotonic(), "success"
            try:
                return await function(*args, **kwargs)
            except asyncio.CancelledError:
                outcome = "cancelled"
                raise
            except Exception as error:
                outcome = _outcome(error)
                raise
            finally:
                telemetry.record(operation, outcome, time.monotonic() - started)
        @wraps(function)
        def synchronous(*args, **kwargs):
            started, outcome = time.monotonic(), "success"
            try:
                result = function(*args, **kwargs)
                if operation == "job.claim" and result is None:
                    outcome = "empty"
                if operation in {"job.complete", "job.fail", "job.heartbeat"} and result is False:
                    outcome = "lease_lost"
                return result
            except Exception as error:
                outcome = _outcome(error)
                raise
            finally:
                telemetry.record(operation, outcome, time.monotonic() - started)
        return asynchronous if iscoroutinefunction(function) else synchronous
    return decorate


class RequestDiagnostics:
    """Pure ASGI middleware: preserves streaming and context across await boundaries."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        with correlation() as value:
            started, outcome = time.monotonic(), "success"
            async def reply(message):
                nonlocal outcome
                if message["type"] == "http.response.start":
                    if message["status"] >= 400:
                        outcome = "error"
                    message = dict(message)
                    message["headers"] = [(k, v) for k, v in message.get("headers", [])
                                          if k.lower() != b"x-correlation-id"] + [(b"x-correlation-id", value.encode())]
                await send(message)
            try:
                await self.app(scope, receive, reply)
            except asyncio.CancelledError:
                outcome = "cancelled"
                raise
            except Exception:
                outcome = "error"
                raise
            finally:
                telemetry.record("api.request", outcome, time.monotonic() - started)
