"""Offline direct transport contracts; no proxy support is introduced."""
import asyncio
from unittest.mock import patch

import httpx
import pytest

from app.sources import eis_rss as a44, eis_223_rss as a223
from app.sources.http import (source_client, ConnectorTransportError, FetchPolicy,
                              bounded_fetch, _RejectedProxyTransport)
from app.sources.http_transport import PublicIPBackend, PublicIPError


@pytest.fixture(autouse=True)
def offline():
    with patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')), patch.object(
            httpx.AsyncHTTPTransport, 'handle_async_request', side_effect=AssertionError('No HTTP')):
        yield


@pytest.mark.parametrize('host', ['zakupki.gov.ru', 'www.b2b-center.ru', 'other.example'])
@pytest.mark.parametrize('proxy', ['http://127.0.0.1:9', 'http://user:secret@proxy.example:80', 'http://proxy.example:80'])
def test_proxy_default_deny(host, proxy):
    async def run():
        async with source_client(trust_env=False, proxy=proxy) as client:
            assert isinstance(client._transport_for_url(httpx.URL('https://' + host)), _RejectedProxyTransport)
            with pytest.raises(ConnectorTransportError):
                await client.get('https://' + host)
    asyncio.run(run())


@pytest.mark.parametrize('url', ['https://other.example/epz/order/extendedsearch/rss.html',
    'http://zakupki.gov.ru/epz/order/extendedsearch/rss.html',
    'https://user:secret@zakupki.gov.ru/epz/order/extendedsearch/rss.html',
    'https://127.0.0.1/epz/order/extendedsearch/rss.html',
    'https://zakupki.gov.ru:444/epz/order/extendedsearch/rss.html'])
def test_direct_official_endpoint_only(url):
    with pytest.raises(a44.SourceError):
        asyncio.run(a44.EisRssSource((url,), direct=True).fetch())


@pytest.mark.parametrize('module,cls,builder', [(a44, a44.EisRssSource, a44.build_eis_rss_url),
    (a223, a223.Eis223RssSource, a223.build_eis_223_rss_url)])
def test_direct_ignores_environment_retains_tls_and_no_redirects(module, cls, builder, monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY', 'http://user:secret@127.0.0.1:9')
    observed = []
    def client(**kwargs):
        observed.append(kwargs)
        return source_client(**kwargs, transport=httpx.MockTransport(lambda request:
            httpx.Response(302, headers={'location': 'https://127.0.0.1/'})))
    with patch.object(module, 'source_client', client), pytest.raises(Exception):
        asyncio.run(cls((builder('test'),), direct=True).fetch())
    assert observed[0]['trust_env'] is False
    assert observed[0]['verify'] is True
    assert observed[0]['follow_redirects'] is False
    assert cls((builder('test'),)).direct is False
    assert cls((builder('test'),), direct=True).for_search_terms(['x']).direct is True


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '::1', '169.254.169.254'])
def test_direct_still_rejects_private_dns(address):
    async def resolver(host, port):
        return ['8.8.8.8', address]
    async def run():
        with pytest.raises(PublicIPError):
            await PublicIPBackend(resolver=resolver).connect_tcp('zakupki.gov.ru', 443)
    asyncio.run(run())


@pytest.mark.parametrize('mode', ['tls', 'cap', 'host'])
def test_existing_bounded_protections(mode):
    def handler(request):
        if mode == 'tls':
            raise httpx.ConnectError('certificate verify failed')
        return httpx.Response(200, content=b'12345')
    async def run():
        with bounded_fetch(FetchPolicy(frozenset({'zakupki.gov.ru'}), 1, max_bytes=4)):
            async with source_client(trust_env=False, verify=True, transport=httpx.MockTransport(handler)) as client:
                with pytest.raises(ConnectorTransportError):
                    await client.get('https://other.example/' if mode == 'host' else a44.EIS_EXTENDED_RSS_URL)
    asyncio.run(run())
