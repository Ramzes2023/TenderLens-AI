"""ARMEPS DNS retry is permitted only for audited resolver failure."""
import httpcore
import httpx

from app.sources.am_armeps import _retryable_official_dns_failure
from app.sources.http_transport import PublicIPError
from app.sources.http import ConnectorTransportError


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


def test_httpx_can_drop_original_os_error_but_keep_exact_httpcore_dns_marker():
    # The GitHub-hosted real official probe observed this two-layer chain.
    core = httpcore.ConnectError("DNS resolution failed")
    wrapped = httpx.ConnectError("DNS resolution failed")
    wrapped.__cause__ = core
    assert _retryable_official_dns_failure(wrapped)
    # A similarly worded outer HTTPX exception alone is not sufficient.
    assert not _retryable_official_dns_failure(httpx.ConnectError("DNS resolution failed"))


def test_bounded_client_wrapper_preserves_genuine_dns_retry_only():
    core = httpcore.ConnectError("DNS resolution failed")
    inner = httpx.ConnectError("DNS resolution failed")
    inner.__cause__ = core
    wrapped = ConnectorTransportError(retryable=True)
    wrapped.__cause__ = inner
    assert _retryable_official_dns_failure(wrapped)
    nonretryable = ConnectorTransportError(retryable=False)
    nonretryable.__cause__ = inner
    assert not _retryable_official_dns_failure(nonretryable)
    no_cause = ConnectorTransportError(retryable=True)
    assert not _retryable_official_dns_failure(no_cause)
    unsafe = ConnectorTransportError(retryable=True)
    unsafe.__cause__ = PublicIPError("Unapproved IP address")
    assert not _retryable_official_dns_failure(unsafe)
    ssl_wrapped = ConnectorTransportError(retryable=True)
    ssl_wrapped.__cause__ = httpx.ConnectError("TLS certificate verification failed")
    assert not _retryable_official_dns_failure(ssl_wrapped)


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


def test_dns_marker_cannot_hide_deeper_security_failure_or_cyclic_chain():
    import ssl
    wrapped = _real_resolver_failure()
    wrapped.__cause__.__cause__ = ssl.SSLCertVerificationError('private TLS diagnostic')
    assert not _retryable_official_dns_failure(wrapped)
    wrapped.__cause__.__cause__ = ConnectorTransportError(retryable=False)
    assert not _retryable_official_dns_failure(wrapped)
    wrapped.__cause__.__cause__ = wrapped
    assert _retryable_official_dns_failure(wrapped)
