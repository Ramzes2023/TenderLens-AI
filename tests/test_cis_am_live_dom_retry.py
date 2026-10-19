"""Offline retry contracts for the strictly pinned official ARMEPS diagnostic.

These synthetic responses are NEVER counted as live procurement evidence.
The real official DOM probe must still parse >=3 current notices or return RED.
"""
import asyncio
import ssl

import httpx
import pytest

from app.sources.http import ConnectorTransportError, source_client as real_source_client
from scripts import ci_cis_am_live_dom_diagnostic as diagnostic


def _install_test_http(monkeypatch, callback):
    def client(**kwargs):
        return real_source_client(**kwargs, transport=httpx.MockTransport(callback))
    monkeypatch.setattr(diagnostic, "source_client", client)


def test_only_a_timeout_cause_can_retry_not_tls_or_broad_transport():
    timeout = httpx.ConnectTimeout("synthetic intermittent connect timeout")
    retryable = ConnectorTransportError(retryable=True)
    retryable.__cause__ = timeout
    assert diagnostic._retryable_observed_timeout(retryable)
    assert not diagnostic._retryable_observed_timeout(ConnectorTransportError(retryable=True))
    nonretry = ConnectorTransportError(retryable=False)
    nonretry.__cause__ = timeout
    assert not diagnostic._retryable_observed_timeout(nonretry)
    certificate = ConnectorTransportError(retryable=True)
    certificate.__cause__ = ssl.SSLCertVerificationError("synthetic certificate failure")
    assert not diagnostic._retryable_observed_timeout(certificate)
    wrapped = ConnectorTransportError(retryable=True)
    wrapped.__cause__ = timeout
    timeout.__cause__ = ssl.SSLError("synthetic nested TLS failure")
    assert not diagnostic._retryable_observed_timeout(wrapped)


def test_diagnostic_retries_one_real_transport_timeout_with_same_strict_origin(monkeypatch):
    requests = []
    def handler(request):
        requests.append(str(request.url))
        if len(requests) == 1:
            raise httpx.ConnectTimeout("synthetic transient timeout")
        return httpx.Response(200, text="<html>synthetic diagnostics only</html>")
    _install_test_http(monkeypatch, handler)
    response, attempts = asyncio.run(diagnostic._fetch_bounded_first_page())
    assert response.status_code == 200 and attempts == 2
    assert requests == [diagnostic.ARMEPS_LISTING_URL] * 2


@pytest.mark.parametrize("status", [403, 503])
def test_diagnostic_never_accepts_or_retries_unsuccessful_http(monkeypatch, status):
    requests = []
    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(status, text="synthetic failed official listing")
    _install_test_http(monkeypatch, handler)
    with pytest.raises(ConnectorTransportError):
        asyncio.run(diagnostic._fetch_bounded_first_page())
    assert requests == [diagnostic.ARMEPS_LISTING_URL]


def test_diagnostic_never_retries_tls_certificate_error(monkeypatch):
    requests = []
    def handler(request):
        requests.append(str(request.url))
        raise ssl.SSLCertVerificationError("synthetic TLS certificate rejection")
    _install_test_http(monkeypatch, handler)
    with pytest.raises(ConnectorTransportError):
        asyncio.run(diagnostic._fetch_bounded_first_page())
    assert requests == [diagnostic.ARMEPS_LISTING_URL]
