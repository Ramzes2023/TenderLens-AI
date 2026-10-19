import json
import ssl

import httpx

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
