"""ARMEPS DNS retry is permitted only for audited resolver failure."""
import httpcore
import httpx

from app.sources.am_armeps import _retryable_official_dns_failure
from app.sources.http_transport import PublicIPError


def _real_resolver_failure():
    try:
        try:
            raise OSError("ephemeral DNS lookup failed")
        except OSError as inner:
            raise httpcore.ConnectError("DNS resolution failed") from inner
    except httpcore.ConnectError as outer:
        wrapped = httpx.ConnectError("DNS resolution failed")
        wrapped.__cause__ = outer
        return wrapped


def test_temporary_dns_retry_only_for_audited_resolver_chain():
    assert _retryable_official_dns_failure(_real_resolver_failure())
    assert not _retryable_official_dns_failure(httpx.ConnectError("DNS resolution failed"))
    assert not _retryable_official_dns_failure(httpx.ConnectError("TCP connection failed"))
    assert not _retryable_official_dns_failure(httpx.ReadTimeout("timeout"))
    assert not _retryable_official_dns_failure(ValueError("invalid host"))


def test_public_ip_policy_violation_not_downgraded_to_retry():
    try:
        raise PublicIPError("Unapproved IP address")
    except PublicIPError as error:
        wrapped = httpx.ConnectError("Unapproved IP address")
        wrapped.__cause__ = error
    assert not _retryable_official_dns_failure(wrapped)


def test_tls_failure_not_reclassified_as_dns_retry():
    import ssl
    try:
        raise ssl.SSLError("CERTIFICATE_VERIFY_FAILED")
    except ssl.SSLError as error:
        wrapped = httpx.ConnectError("Connect error")
        wrapped.__cause__ = error
    assert not _retryable_official_dns_failure(wrapped)
