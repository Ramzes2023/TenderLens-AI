"""OFFLINE ARMEPS first-party reset transport boundary; no tender data or live proof."""
import asyncio
import ssl

import httpx
import pytest

import app.sources.am_armeps as am
from app.sources.eis_rss import SourceError
from app.sources.http import ConnectorTransportError, source_client
from app.sources.transport_errors import SourceTransportError


def install(monkeypatch, cause):
    calls = []
    def network(request):
        assert str(request.url) == am.ARMEPS_LISTING_URL
        calls.append(str(request.url))
        try:
            raise cause
        except BaseException as underlying:
            raise httpx.ConnectError("synthetic source transport", request=request) from underlying

    monkeypatch.setattr(
        am, "source_client",
        lambda **opts: source_client(**opts, transport=httpx.MockTransport(network)),
    )
    return calls


def test_first_party_tcp_reset_is_retryable_from_bounded_client(monkeypatch):
    calls = install(monkeypatch, ConnectionResetError(104, "synthetic reset"))
    with pytest.raises(SourceTransportError, match="Temporary source transport failure"):
        asyncio.run(am.ArmeniaArmepsSource().fetch(limit=1))
    assert calls == [am.ARMEPS_LISTING_URL]


@pytest.mark.parametrize("cause", [
    OSError("unknown transport error"),
    ssl.SSLCertVerificationError(1, "synthetic invalid certificate"),
])
def test_unclassified_or_tls_connect_errors_remain_permanent(monkeypatch, cause):
    calls = install(monkeypatch, cause)
    with pytest.raises(SourceError) as error:
        asyncio.run(am.ArmeniaArmepsSource().fetch(limit=1))
    assert not isinstance(error.value, SourceTransportError)
    assert calls == [am.ARMEPS_LISTING_URL]


def test_policy_rejection_and_tls_never_get_network_reset_retry():
    try:
        try:
            raise ConnectionResetError(104, "synthetic reset")
        except ConnectionResetError as reset:
            raise httpx.ConnectError("synthetic") from reset
    except httpx.ConnectError as network:
        with pytest.raises(ConnectorTransportError):
            try:
                raise ConnectorTransportError(retryable=False, reason="public_ip") from network
            except ConnectorTransportError as rejected:
                assert am._retryable_official_peer_reset(rejected) is False
                raise

    try:
        try:
            raise ConnectionResetError(104, "synthetic reset")
        except ConnectionResetError as reset:
            raise httpx.ConnectError("synthetic") from reset
    except httpx.ConnectError as network:
        try:
            raise ConnectorTransportError(retryable=True, reason="tls_certificate") from network
        except ConnectorTransportError as tls:
            assert am._retryable_official_peer_reset(tls) is False
        try:
            raise ConnectorTransportError(retryable=True, reason="network") from network
        except ConnectorTransportError as verified_network:
            assert am._retryable_official_peer_reset(verified_network) is True
