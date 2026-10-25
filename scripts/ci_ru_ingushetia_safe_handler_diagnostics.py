"""Isolated CI-only exception class telemetry around the *real* queue handler.

No source monkeypatching, no bypass, no raw traceback or exception string.
Only the class name from a closed allowlist is recorded before the durable
Worker handles it normally. Live success criteria are completely unchanged.
"""
from app.sources.ingestion import ConnectorSyncHandler
from scripts.ru_transport_diagnostics import transport_failure

_ALLOWED = frozenset({
    "ConnectorTransportError", "ConnectError", "ConnectTimeout", "ReadError",
    "ReadTimeout", "TimeoutError", "SourceError", "SourceTransportError",
    "HTTPStatusError", "ValueError", "TypeError", "AssertionError",
    "KeyError", "AttributeError", "RuntimeError", "StorageError",
    "StorageIntegrityError", "OperationalError", "IntegrityError",
    "RetryableJobError", "PermanentJobError", "OverflowError",
})


# Diagnostic classifications only. Never include the original exception
# message, hostname, IP, URL, payload or credentials.
_CATEGORY_ALLOWLIST = frozenset({
    "unclassified", "tls_certificate_verification",
    "response_read_timeout", "response_read_failure",
    "connection_or_tls_handshake_timeout", "connection_failure_unspecified",
})
SAFE_FAILURE_CATEGORIES = _CATEGORY_ALLOWLIST | frozenset({
    "handler_other", "handler_without_upstream_context",
    "upstream_http_429", "upstream_http_5xx", "upstream_http_other",
    "source_contract_or_schema", "durable_storage",
})


def sanitize_failure_categories(categories):
    """Never pass through arbitrary strings supplied by an exception."""
    return tuple(label if type(label) is str and label in SAFE_FAILURE_CATEGORIES
                 else "handler_other" for label in tuple(categories)[-3:])



def safe_handler_failure_category(error):
    """Diagnose wrapped upstream error without changing real Worker semantics."""
    if type(error).__name__ not in {"RetryableJobError", "PermanentJobError"}:
        return "handler_other"
    upstream = getattr(error, "__context__", None)
    if upstream is None:
        return "handler_without_upstream_context"
    upstream_class = type(upstream).__name__
    if upstream_class in {
        "ConnectorTransportError", "ConnectError", "ConnectTimeout",
        "ReadError", "ReadTimeout", "TimeoutError", "SourceTransportError",
    }:
        result = transport_failure(upstream)
        category = result["category"]
        return category if category in _CATEGORY_ALLOWLIST else "unclassified"
    if upstream_class == "HTTPStatusError":
        response = getattr(upstream, "response", None)
        status = getattr(response, "status_code", None)
        return ("upstream_http_429" if status == 429 else
                "upstream_http_5xx" if type(status) is int and 500 <= status <= 599 else
                "upstream_http_other")
    if upstream_class in {"SourceError", "ValueError", "TypeError", "WorldBankSourceError"}:
        return "source_contract_or_schema"
    if upstream_class in {"StorageError", "StorageIntegrityError", "OperationalError", "IntegrityError"}:
        return "durable_storage"
    return "handler_other"


class DiagnosticConnectorHandler:
    def __init__(self, handler):
        if not isinstance(handler, ConnectorSyncHandler):
            raise TypeError("Only actual production connector handler accepted")
        self.handler = handler
        self.failure_classes = []
        self.failure_categories = []
        self.failure_errno_sets = []

    def __call__(self, context, payload):
        try:
            return self.handler(context, payload)
        except Exception as error:
            name = type(error).__name__
            self.failure_classes.append(name if name in _ALLOWED else "OTHER")
            self.failure_categories.append(safe_handler_failure_category(error))
            # OS errno is a fixed numeric API field, unlike raw exception
            # strings, IPs, hostnames, headers or upstream responses. Enforce
            # a small finite range; do not print traceback or exception text.
            upstream = getattr(error, "__context__", None)
            report = transport_failure(upstream) if upstream is not None else {}
            codes = report.get("os_error_numbers", ())
            self.failure_errno_sets.append(tuple(
                x for x in codes[:4] if type(x) is int and 0 <= x <= 100000
            ))
            raise


def safe_handler_failure_classes(handler):
    return tuple(handler.failure_classes[-3:])


def safe_handler_failure_categories(handler):
    return sanitize_failure_categories(handler.failure_categories)


def safe_handler_failure_errnos(handler):
    """Return at most three redacted numeric OS errno tuples, not error text."""
    return tuple(tuple(code for code in group[:4]
                       if type(code) is int and 0 <= code <= 100000)
                 for group in handler.failure_errno_sets[-3:])
