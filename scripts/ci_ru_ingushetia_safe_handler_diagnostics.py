"""Isolated CI-only exception class telemetry around the *real* queue handler.

No source monkeypatching, no bypass, no raw traceback or exception string.
Only the class name from a closed allowlist is recorded before the durable
Worker handles it normally. Live success criteria are completely unchanged.
"""
from app.sources.ingestion import ConnectorSyncHandler

_ALLOWED = frozenset({
    "ConnectorTransportError", "ConnectError", "ConnectTimeout", "ReadError",
    "ReadTimeout", "TimeoutError", "SourceError", "SourceTransportError",
    "HTTPStatusError", "ValueError", "TypeError", "AssertionError",
    "KeyError", "AttributeError", "RuntimeError", "StorageError",
    "StorageIntegrityError", "OperationalError", "IntegrityError",
    "RetryableJobError", "PermanentJobError", "OverflowError",
})


class DiagnosticConnectorHandler:
    def __init__(self, handler):
        if not isinstance(handler, ConnectorSyncHandler):
            raise TypeError("Only actual production connector handler accepted")
        self.handler = handler
        self.failure_classes = []

    def __call__(self, context, payload):
        try:
            return self.handler(context, payload)
        except Exception as error:
            name = type(error).__name__
            self.failure_classes.append(name if name in _ALLOWED else "OTHER")
            raise


def safe_handler_failure_classes(handler):
    return tuple(handler.failure_classes[-3:])
