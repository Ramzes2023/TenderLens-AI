"""Offline RU10 contracts. All XML/proxy credentials below are synthetic."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app.sources import eis_rss as a44, eis_223_rss as a223
from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client
from app.sources.http_transport import PublicIPBackend, PublicIPError

spec = importlib.util.spec_from_file_location('ru10_smoke', Path(__file__).with_name('ru10_eis_live_smoke.py'))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


@pytest.fixture(autouse=True)
def offline():
    with patch('socket.getaddrinfo', side_effect=AssertionError('No real DNS')), \
         patch.object(httpx.AsyncHTTPTransport, 'handle_async_request',
                      side_effect=AssertionError('No real HTTP')):
        yield


def item(law, identity='SYNTHETIC_RU10', label=True):
    route = ('/epz/order/notice/ea44/view/common-info.html' if law == '44'
             else '/223/purchase/public/purchase/info/common-info.html')
    description = ('Найденный результат: Размещение выполняется по: ' + law + '-ФЗ'
                   if label else 'Параметры поиска: 223-ФЗ и 44-ФЗ')
    return (f'<item><guid>{identity}</guid><title>Синтетическая поставка</title>'
            f'<link>https://zakupki.gov.ru{route}?regNumber=1234567890123456789</link>'
            f'<description>{description}</description></item>')


def feed(*items):
    return ('<rss><channel>' + ''.join(items) + '</channel></rss>').encode()


def mock_adapter(monkeypatch, module, payload, status=200):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, content=payload,
                              headers={'location': 'https://127.0.0.1/forbidden'})
    def client(**kwargs):
        return source_client(**dict(kwargs, trust_env=False, transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(module, 'source_client', client)
    return calls


@pytest.mark.parametrize('proxy', [
    'http://127.0.0.1:9', 'http://10.0.0.1:9', 'http://[::1]:9',
    'http://proxy.example:8080', 'https://proxy.example:443',
    'socks5://proxy.example:1080',
    'http://synthetic-user:synthetic-secret@proxy.example:8080',
])
def test_no_proxy_is_implicitly_vetted(monkeypatch, tmp_path, proxy):
    def client(**kwargs):
        return source_client(**dict(kwargs, trust_env=False, proxy=proxy))
    for module in (a44, a223):
        monkeypatch.setattr(module, 'source_client', client)
    result = asyncio.run(smoke.run(tmp_path))
    for key, entry in result['sources'].items():
        assert entry['state'] == 'BLOCKED'
        assert entry['real_records'] == entry['database_upserts'] == entry['query_matches'] == 0
        assert entry['law_verified'] is False
        assert result['diagnostics'][key]['proxy_route_rejected'] is True
        assert result['diagnostics'][key]['exception_type'] == 'ConnectorTransportError'
    serialized = json.dumps(result)
    assert proxy not in serialized
    assert 'synthetic-user' not in serialized and 'synthetic-secret' not in serialized


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '::1', '169.254.169.254'])
def test_mixed_dns_denied_before_tcp(address):
    async def resolver(host, port):
        return ['8.8.8.8', address]
    class NoTCP:
        async def connect_tcp(self, *args, **kwargs):
            pytest.fail('Private DNS must fail before TCP')
    async def run():
        with pytest.raises(PublicIPError):
            await PublicIPBackend(resolver=resolver, tcp_backend=NoTCP()).connect_tcp('zakupki.gov.ru', 443)
    asyncio.run(run())


@pytest.mark.parametrize('status', [301, 302, 307, 308])
def test_eis_bounded_redirect_denied(monkeypatch, tmp_path, status):
    calls = [mock_adapter(monkeypatch, module, b'', status) for module in (a44, a223)]
    result = asyncio.run(smoke.run(tmp_path))
    assert all(entry['state'] == 'BLOCKED' for entry in result['sources'].values())
    assert all(len(group) == 1 and group[0].url.host == 'zakupki.gov.ru' for group in calls)


@pytest.mark.parametrize('kind', ['wrong', 'mixed', 'unknown', 'late_wrong', 'conflict'])
def test_entire_feed_law_gate_precedes_storage(monkeypatch, tmp_path, kind):
    for module, law, other in ((a44, '44', '223'), (a223, '223', '44')):
        payloads = {
            'wrong': feed(item(other)),
            'mixed': feed(item(law), item(other, 'OTHER')),
            'unknown': feed(item(law, label=False)),
            'late_wrong': feed(*(item(law, str(i)) for i in range(25)), item(other, 'LATE')),
            'conflict': feed(item(law), item(law).replace(f'по: {law}-ФЗ', f'по: {other}-ФЗ')),
        }
        mock_adapter(monkeypatch, module, payloads[kind])
    with patch('app.sources.opportunities.OpportunityRepository.initialize',
               side_effect=AssertionError('No database for rejected law')):
        result = asyncio.run(smoke.run(tmp_path))
    for entry in result['sources'].values():
        assert entry['state'] == 'BLOCKED' and entry['reason'].startswith('Law blocked:')
        assert entry['real_records'] == entry['database_upserts'] == entry['query_matches'] == 0
        assert entry['law_verified'] is False


def test_matching_law_adapter_sqlite_snapshot_branch(monkeypatch, tmp_path):
    # Synthetic branch verification only; this test is never live evidence.
    for module, law in ((a44, '44'), (a223, '223')):
        mock_adapter(monkeypatch, module, feed(item(law), item(law)))
    result = asyncio.run(smoke.run(tmp_path))
    for entry in result['sources'].values():
        assert entry['state'] == 'LIVE_E2E_VERIFIED'
        assert entry['real_records'] == entry['database_upserts'] == entry['query_matches'] == 1
        assert entry['law_verified'] is True
    assert result['ai_query_verified'] is False


def test_host_allowlist_precedes_dispatch():
    calls = []
    async def run():
        with bounded_fetch(FetchPolicy(frozenset({'zakupki.gov.ru'}), 1)):
            async with source_client(trust_env=False, transport=httpx.MockTransport(calls.append)) as client:
                with pytest.raises(ConnectorTransportError):
                    await client.get('https://other.example/feed')
    asyncio.run(run())
    assert calls == []


def test_environment_proxy_is_denied_and_redacted(monkeypatch, tmp_path):
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
                 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('HTTPS_PROXY', 'http://synthetic-user:synthetic-secret@127.0.0.1:9')
    result = asyncio.run(smoke.run(tmp_path))
    assert all(entry['state'] == 'BLOCKED' for entry in result['sources'].values())
    assert all(info['proxy_route_rejected'] is True for info in result['diagnostics'].values())
    assert 'synthetic-secret' not in json.dumps(result)
    assert 'synthetic-user' not in json.dumps(result)


@pytest.mark.parametrize('law,sha256', [
    ('44', 'af02e38f6a59802c380e12553c6f732db0099ca11548a36c16d6699cd36fd06a'),
    ('223', '9b91ba812d901227179b38be896c1f67be9c5187bbd5c3fbf0cefc333bc8094a'),
])
def test_optional_exact_host_capture_is_offline_only(law, sha256):
    configured = os.environ.get('RU10_EIS_EVIDENCE_' + law)
    if not configured:
        pytest.skip('Optional genuine HOST TEMP capture not configured')
    info = smoke.external_evidence(Path(configured))
    assert info['sha256'] == sha256
    assert info['record_links'] == info['law_223_links'] == 200
    assert info['law_44_links'] == 0
    assert info['live_proof'] is False
