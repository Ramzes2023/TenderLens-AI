"""OFFLINE transport regression; only live official Worker/SQL proves delivery."""
import asyncio
import ssl
from contextlib import asynccontextmanager

import httpx
import pytest

import app.sources.az_azeristilik as az
from app.sources.eis_rss import SourceError
from app.sources.transport_errors import SourceTransportError


@pytest.mark.parametrize("cause,should_retry", [
    (ConnectionResetError(104, "peer reset"), True),
    (ssl.SSLError("certificate verification failure"), False),
    (OSError("unknown connect error"), False),
])
def test_only_verified_tcp_connection_reset_is_retryable(monkeypatch, cause, should_retry):
    def response(request):
        raise httpx.ConnectError("official connection unavailable", request=request) from cause

    @asynccontextmanager
    async def official_client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        async with httpx.AsyncClient(transport=httpx.MockTransport(response), **kwargs) as client:
            yield client

    monkeypatch.setattr(az, "source_client", official_client)
    if should_retry:
        with pytest.raises(SourceTransportError, match="temporarily unavailable"):
            asyncio.run(az.AzerbaijanHeatSource().fetch(limit=1))
    else:
        with pytest.raises(SourceError, match="verified official HTTPS retrieval failed") as info:
            asyncio.run(az.AzerbaijanHeatSource().fetch(limit=1))
        assert not isinstance(info.value, SourceTransportError)


def test_nested_tcp_reset_is_retryable_without_relaxing_first_party_policy():
    try:
        try:
            raise ConnectionResetError(104, "reset")
        except ConnectionResetError as cause:
            raise RuntimeError("http transport wrapper") from cause
    except RuntimeError as wrapper:
        try:
            raise httpx.ConnectError("opaque connection error") from wrapper
        except httpx.ConnectError as error:
            assert az._official_peer_reset(error) is True


def test_bounded_transport_wrapped_reset_retries_but_policy_rejection_does_not():
    from app.sources.http import ConnectorTransportError
    try:
        try:
            raise ConnectionResetError(104, "reset")
        except ConnectionResetError as error:
            raise httpx.ConnectError("bounded official client") from error
    except httpx.ConnectError as connect:
        try:
            raise ConnectorTransportError(retryable=True, reason="network") from connect
        except ConnectorTransportError as wrapped:
            assert az._official_peer_reset(wrapped) is True
        try:
            raise ConnectorTransportError(retryable=False, reason="public_ip") from connect
        except ConnectorTransportError as blocked:
            assert az._official_peer_reset(blocked) is False
        try:
            raise ConnectorTransportError(retryable=False, reason="tls_certificate") from connect
        except ConnectorTransportError as blocked:
            assert az._official_peer_reset(blocked) is False
