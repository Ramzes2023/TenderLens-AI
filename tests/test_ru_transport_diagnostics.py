import json
import ssl

import httpx
import pytest

from scripts.ru_transport_diagnostics import transport_failure


def test_nested_certificate_failure_is_distinct_and_redacted():
    cert = ssl.SSLCertVerificationError(1, "secret-token must never appear")
    cert.verify_code = 20
    inner = httpx.ConnectError("secret URL")
    inner.__context__ = cert
    outer = RuntimeError("secret chat")
    outer.__cause__ = inner
    result = transport_failure(outer)
    assert result["category"] == "tls_certificate_verification"
    assert result["certificate_verify_code"] == 20
    assert "secret" not in json.dumps(result)


def test_timeouts_do_not_claim_certificate_failure_and_cycles_terminate():
    for error, expected in (
        (httpx.ReadTimeout("private"), "response_read_timeout"),
        (httpx.ReadError("private"), "response_read_failure"),
        (httpx.ConnectTimeout("private"), "connection_or_tls_handshake_timeout"),
        (httpx.ConnectError("private"), "connection_failure_unspecified"),
    ):
        error.__cause__ = error
        result = transport_failure(error)
        assert result["category"] == expected
        assert result["certificate_verify_code"] is None


def test_known_ingushetia_vendor_failures_are_classified_without_remote_text():
    from scripts.ci_ru_ingushetia_live_worker import _safe_ingushetia_vendor_failure

    assert _safe_ingushetia_vendor_failure(ValueError(
        "No source-owned Ingushetia committee tenders in live Fabrikant list"
    )) == "REGIONAL_ROWS_ABSENT"
    assert _safe_ingushetia_vendor_failure(ValueError(
        "No independently verified regional original cards"
    )) == "ORIGINAL_CARDS_NOT_VERIFIED"
    assert _safe_ingushetia_vendor_failure(ValueError(
        "First-party regional listing was not HTML"
    )) == "LISTING_NOT_HTML"
    assert _safe_ingushetia_vendor_failure(ValueError(
        "Untrusted Fabrikant regional listing"
    )) == "LISTING_UNTRUSTED"
    assert _safe_ingushetia_vendor_failure(ValueError(
        "secret upstream query and token=ABC"
    )) is None
    assert _safe_ingushetia_vendor_failure(RuntimeError("private")) is None


def test_nested_os_socket_error_codes_are_safe_and_numeric_only():
    error = httpx.ConnectError("private URL /?token=SHOULD_NOT_LOG")
    socket_error = ConnectionRefusedError(10061, "private destination")
    error.__cause__ = socket_error
    result = transport_failure(error)
    assert result["category"] == "connection_failure_unspecified"
    assert result["os_error_numbers"] == [10061]
    assert "private" not in json.dumps(result)
    assert "SHOULD_NOT_LOG" not in json.dumps(result)


def test_fabrikant_worker_failure_reports_only_allowlisted_job_outcome():
    from types import SimpleNamespace
    from scripts.ci_ru_ingushetia_fabrikant_worker import IngushetiaWorkerProofFailure
    from scripts.ci_ru_ingushetia_live_worker import _safe_ingushetia_vendor_failure

    retry = IngushetiaWorkerProofFailure(
        SimpleNamespace(state="queued", failure_code="retryable_failure")
    )
    assert _safe_ingushetia_vendor_failure(retry) == "WORKER_FAILED"
    assert retry.job_state == "queued"
    assert retry.job_failure_code == "retryable_failure"

    unsafe = IngushetiaWorkerProofFailure(
        SimpleNamespace(state="private status", failure_code="token=PRIVATE")
    )
    assert unsafe.job_state == "UNKNOWN"
    assert unsafe.job_failure_code == "UNKNOWN"
    assert "PRIVATE" not in str(unsafe)


def test_ci_handler_exception_telemetry_preserves_failure_and_redacts_strings():
    from scripts.ci_ru_ingushetia_safe_handler_diagnostics import (
        DiagnosticConnectorHandler, safe_handler_failure_classes,
    )
    from app.sources.ingestion import ConnectorSyncHandler

    class BrokenSource:
        def __call__(self, context, payload):
            raise ValueError("https://private.invalid/?token=SECRET")

    class CapturingDiagnostic(DiagnosticConnectorHandler):
        pass

    # The wrapper accepts only a *real* connector handler at setup. Bypass
    # only its handler field AFTER construction for an offline test seam.
    base = object.__new__(ConnectorSyncHandler)
    wrapper = CapturingDiagnostic(base)
    wrapper.handler = BrokenSource()
    with pytest.raises(ValueError):
        wrapper(None, None)
    assert safe_handler_failure_classes(wrapper) == ("ValueError",)
    assert "SECRET" not in repr(safe_handler_failure_classes(wrapper))
    assert "private.invalid" not in repr(safe_handler_failure_classes(wrapper))


def test_safe_ingushetia_handler_diagnoses_wrapped_network_cause_without_leaking_urls():
    from app.jobs.worker import RetryableJobError
    from app.sources.ingestion import ConnectorSyncHandler
    from scripts.ci_ru_ingushetia_safe_handler_diagnostics import (
        DiagnosticConnectorHandler, safe_handler_failure_classes,
        safe_handler_failure_categories,
    )

    class RealExceptionShape:
        def __call__(self, context, payload):
            try:
                raise httpx.ConnectTimeout("SECRET https://private.invalid/?token=ABC")
            except httpx.ConnectTimeout:
                raise RetryableJobError("SECRET-UPSTREAM-PAYLOAD") from None

    wrapper = DiagnosticConnectorHandler(object.__new__(ConnectorSyncHandler))
    wrapper.handler = RealExceptionShape()
    with pytest.raises(RetryableJobError):
        wrapper(None, None)
    assert safe_handler_failure_classes(wrapper) == ("RetryableJobError",)
    assert safe_handler_failure_categories(wrapper) == ("connection_or_tls_handshake_timeout",)
    assert "SECRET" not in repr(safe_handler_failure_categories(wrapper))
    assert "private.invalid" not in repr(safe_handler_failure_categories(wrapper))


def test_safe_ingushetia_handler_categories_fail_closed_on_arbitrary_values():
    from types import SimpleNamespace
    from scripts.ci_ru_ingushetia_safe_handler_diagnostics import (
        sanitize_failure_categories, safe_handler_failure_category,
    )
    from scripts.ci_ru_ingushetia_fabrikant_worker import IngushetiaWorkerProofFailure
    from scripts.ci_ru_ingushetia_live_worker import IngushetiaEisWorkerFailure

    kinds = ["response_read_timeout", "token=SECRET", "tls_certificate_verification"]
    assert sanitize_failure_categories(kinds) == (
        "response_read_timeout", "handler_other", "tls_certificate_verification",
    )
    assert safe_handler_failure_category(ValueError("https://private.invalid")) == "handler_other"
    dummy = SimpleNamespace(state="failed", failure_code="handler_error")
    for constructor in (IngushetiaWorkerProofFailure, IngushetiaEisWorkerFailure):
        value = constructor(dummy, ("RetryableJobError",), kinds)
        assert value.handler_failure_categories == (
            "response_read_timeout", "handler_other", "tls_certificate_verification",
        )
        assert "SECRET" not in repr(value.handler_failure_categories)
        assert "SECRET" not in str(value)


def test_exactly_three_wrapped_transient_failures_are_classified_as_network_exhaustion():
    from scripts.ci_ru_ingushetia_safe_handler_diagnostics import classify_failed_live_worker

    classes = ("RetryableJobError",) * 3
    causes = (
        "connection_failure_unspecified",
        "connection_or_tls_handshake_timeout",
        "response_read_failure",
    )
    assert classify_failed_live_worker(classes, causes) == "UPSTREAM_NETWORK_RETRIES_EXHAUSTED"
    assert classify_failed_live_worker(classes[:2], causes[:2]) == "UNDETERMINED_FAILURE"
    assert classify_failed_live_worker(("RetryableJobError", "TypeError", "RetryableJobError"), causes) == "UNDETERMINED_FAILURE"
    assert classify_failed_live_worker(classes, causes[:2] + ("source_contract_or_schema",)) == "SOURCE_CONTRACT_FAILURE_OBSERVED"
    assert classify_failed_live_worker(classes, causes[:2] + ("durable_storage",)) == "DURABLE_STORAGE_FAILURE_OBSERVED"
    assert classify_failed_live_worker(classes, causes[:2] + ("token=SECRET",)) == "UNDETERMINED_FAILURE"
    assert "SECRET" not in classify_failed_live_worker(classes, causes[:2] + ("token=SECRET",))
