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
        (httpx.ConnectTimeout("private"), "connection_or_tls_handshake_timeout"),
        (httpx.ConnectError("private"), "connection_failure_unspecified"),
    ):
        error.__cause__ = error
        result = transport_failure(error)
        assert result["category"] == expected
        assert result["certificate_verify_code"] is None
