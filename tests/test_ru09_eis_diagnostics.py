"""RU09 offline tests of production adapters; generated XML is SYNTHETIC.

Optional RU09_EIS_EVIDENCE points to genuine external HOST TEMP bytes. No live
requests in pytest, no captured host bytes are checked into this repository.
"""
import asyncio
import importlib.util
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.sources import eis_rss as a44, eis_223_rss as a223
from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client
from app.sources.ru08_integration import local_catalog

spec = importlib.util.spec_from_file_location('ru09_smoke', Path(__file__).with_name('ru09_eis_live_smoke.py'))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def synthetic_feed(law='44', repeat=1, label=True):
    """Explicitly synthetic record, never evidence of actual coverage."""
    route = '/epz/order/notice/ea44/view/common-info.html' if law == '44' else '/223/purchase/public/purchase/info/common-info.html'
    description = ('Найденный результат: Размещение выполняется по: ' + law + '-ФЗ') if label else 'Параметры поиска: Закупки по: 223-ФЗ и 44-ФЗ'
    item = f'<item><guid>RU09_SYNTHETIC_1</guid><title>Синтетическая поставка</title><link>https://zakupki.gov.ru{route}?regNumber=1234567890123456789</link><description>{description}</description></item>'
    return ('<rss><channel>' + item * repeat + '</channel></rss>').encode()


def adapter(module):
    return (a44.EisRssSource((a44.build_eis_rss_url('поставка'),)) if module is a44
            else a223.Eis223RssSource((a223.build_eis_223_rss_url('поставка'),)))


def install_mock(monkeypatch, module, handler):
    calls = []

    def dispatch(request):
        calls.append(request)
        return handler(request)

    def client(**kwargs):
        return source_client(**dict(kwargs, trust_env=False, transport=httpx.MockTransport(dispatch)))

    monkeypatch.setattr(module, 'source_client', client)
    return calls


def test_exact_urls_and_default_off():
    urls = [a44.build_eis_rss_url('поставка'), a223.build_eis_223_rss_url('поставка')]
    assert all(urlsplit(url).hostname == 'zakupki.gov.ru' for url in urls)
    assert all(urlsplit(url).path == '/epz/order/extendedsearch/rss.html' for url in urls)
    assert parse_qs(urlsplit(urls[0]).query)['fz44'] == ['on']
    assert 'fz223' not in parse_qs(urlsplit(urls[0]).query)
    assert parse_qs(urlsplit(urls[1]).query)['fz223'] == ['on']
    assert 'fz44' not in parse_qs(urlsplit(urls[1]).query)
    assert 'eis_223' not in local_catalog().enabled_keys


@pytest.mark.parametrize('law', ['44', '223'])
def test_identity_is_not_law_verification(law):
    payload = synthetic_feed(law)
    n44 = a44.parse_eis_feed(payload)[0]
    n223 = a223.parse_eis_223_feed(payload, feed_url=a223.build_eis_223_rss_url('поставка'))[0]
    assert n44.identity == ('eis', 'RU09_SYNTHETIC_1')
    assert n223.identity == ('eis_223', 'RU09_SYNTHETIC_1')
    assert n44.url == n223.url
    assert n223.requested_law == '223-FZ'
    assert n223.observed_law == law + '-FZ'
    assert n223.independently_verified_law is None
    assert smoke.law_evidence(payload)[n44.url] == law + '-FZ'


def test_law_requires_record_label_and_matching_route():
    assert set(smoke.law_evidence(synthetic_feed(label=False)).values()) == {None}
    mismatch = synthetic_feed('223').replace('по: 223-ФЗ'.encode(), 'по: 44-ФЗ'.encode())
    assert set(smoke.law_evidence(mismatch).values()) == {None}
    assert set(smoke.law_evidence(synthetic_feed().replace(b'zakupki.gov.ru', b'example.test')).values()) == {None}
    with pytest.raises(ValueError):
        smoke.law_evidence(b'<!DOCTYPE rss><rss/>')


@pytest.mark.parametrize('payload', [b'<!DOCTYPE rss><rss/>',
    b'<!DOCTYPE rss [<!ENTITY x "synthetic">]><rss/>',
    '<!DOCTYPE rss><rss/>'.encode('utf-16')])
def test_existing_223_dtd_control_is_preserved(payload):
    with pytest.raises(a44.SourceError):
        a223.parse_eis_223_feed(payload)


@pytest.mark.parametrize('module', [a44, a223])
def test_existing_bounded_host_policy_precedes_dispatch(monkeypatch, module):
    calls = install_mock(monkeypatch, module, lambda request: httpx.Response(200, content=synthetic_feed()))
    # Even a valid official adapter URL is rejected by a nonmatching policy.
    with bounded_fetch(FetchPolicy(frozenset({'example.test'}), 1)):
        with pytest.raises(ConnectorTransportError) as caught:
            asyncio.run(adapter(module).fetch())
    assert caught.value.retryable is False
    assert calls == []


@pytest.mark.parametrize('module', [a44, a223])
def test_html_200_is_not_rss_success(monkeypatch, module):
    calls = install_mock(monkeypatch, module, lambda request: httpx.Response(200,
        headers={'content-type': 'text/html'}, content=b'<!doctype html><html>synthetic denial</html>'))
    with bounded_fetch(FetchPolicy(frozenset({'zakupki.gov.ru'}), 1)):
        with pytest.raises(a44.SourceError):
            asyncio.run(adapter(module).fetch())
    assert len(calls) == 1


@pytest.mark.parametrize('module', [a44, a223])
def test_actual_adapter_dedup_and_tls(monkeypatch, module):
    configs = []
    payload = synthetic_feed('44' if module is a44 else '223', repeat=2)
    original = module.source_client

    def client(**kwargs):
        configs.append(kwargs)
        return original(**dict(kwargs, trust_env=False, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=payload, headers={'content-type': 'application/rss+xml'}))))

    monkeypatch.setattr(module, 'source_client', client)
    with bounded_fetch(FetchPolicy(frozenset({'zakupki.gov.ru'}), 1, max_bytes=smoke.MAX_BYTES)):
        notices = asyncio.run(adapter(module).fetch())
    assert len(notices) == 1
    assert configs[0]['verify'] is True and configs[0]['trust_env'] is True
    assert notices[0].source == ('eis' if module is a44 else 'eis_223')


@pytest.mark.parametrize('module', [a44, a223])
@pytest.mark.parametrize('status,retryable', [(403, False), (302, False), (408, True), (429, True), (503, True)])
def test_bounded_http_outcomes_no_adapter_retries(monkeypatch, module, status, retryable):
    calls = install_mock(monkeypatch, module, lambda request: httpx.Response(status,
        headers={'location': 'https://example.test/denied'}, content=b''))
    with bounded_fetch(FetchPolicy(frozenset({'zakupki.gov.ru'}), 1)):
        with pytest.raises(ConnectorTransportError) as caught:
            asyncio.run(adapter(module).fetch())
    assert caught.value.retryable is retryable
    assert len(calls) == 1  # Retry classification is retained; adapters do not retry.
    assert calls[0].url.host == 'zakupki.gov.ru'


@pytest.mark.parametrize('module', [a44, a223])
def test_selected_proxy_fails_closed_before_any_network(monkeypatch, module):
    # Explicit synthetic proxy simulates an environment-selected route, without
    # reading or printing the user's proxy config. Real shared client is retained.
    def client(**kwargs):
        return source_client(**dict(kwargs, trust_env=False, proxy='http://127.0.0.1:9'))

    monkeypatch.setattr(module, 'source_client', client)
    with bounded_fetch(FetchPolicy(frozenset({'zakupki.gov.ru'}), 1)):
        with pytest.raises(ConnectorTransportError) as caught:
            asyncio.run(adapter(module).fetch())
    assert caught.value.retryable is False
    assert str(caught.value) == 'Connector transport failed.'


@pytest.mark.parametrize('module', [a44, a223])
def test_environment_proxy_route_and_no_proxy_selection(monkeypatch, module):
    # Isolate only HTTPX proxy-routing variables; never inspect credentials.
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
                 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:9')
    diagnostics = {}
    with bounded_fetch(FetchPolicy(frozenset({'zakupki.gov.ru'}), 1)):
        with smoke.observe_adapter(module, adapter(module).urls[0], diagnostics):
            with pytest.raises(ConnectorTransportError):
                asyncio.run(adapter(module).fetch())
    assert diagnostics['proxy_route_rejected'] is True
    monkeypatch.setenv('NO_PROXY', 'zakupki.gov.ru')
    from app.sources.http import _RejectedProxyTransport
    # Route inspection only: NO_PROXY is NOT permission to bypass host policy.
    async def inspect():
        async with source_client(trust_env=True) as client:
            return isinstance(client._transport_for_url(httpx.URL(adapter(module).urls[0])), _RejectedProxyTransport)
    assert asyncio.run(inspect()) is False


def test_synthetic_smoke_roundtrip_is_test_only(monkeypatch, tmp_path):
    install_mock(monkeypatch, a44, lambda request: httpx.Response(200, content=synthetic_feed('44')))
    install_mock(monkeypatch, a223, lambda request: httpx.Response(200, content=synthetic_feed('223')))
    report = asyncio.run(smoke.run(tmp_path))
    assert report['ai_query_verified'] is False
    for entry in report['sources'].values():
        assert entry['state'] == 'LIVE_E2E_VERIFIED'  # Mocked branch test, never live evidence.
        assert entry['real_records'] == entry['database_upserts'] == entry['query_matches'] == 1
        assert entry['law_verified'] is True


def test_wrong_law_never_promotes_to_e2e(monkeypatch, tmp_path):
    install_mock(monkeypatch, a44, lambda request: httpx.Response(200, content=synthetic_feed('223')))
    install_mock(monkeypatch, a223, lambda request: httpx.Response(200, content=synthetic_feed('44')))
    report = asyncio.run(smoke.run(tmp_path))
    for entry in report['sources'].values():
        assert entry['state'] == 'LIVE_FETCH_ONLY'
        assert entry['law_verified'] is False
        assert entry['real_records'] == 1
        assert entry['database_upserts'] == entry['query_matches'] == 0


def test_proxy_blocked_smoke_has_safe_details(monkeypatch, tmp_path):
    def client(**kwargs):
        return source_client(**dict(kwargs, trust_env=False, proxy='http://127.0.0.1:9'))
    for module in (a44, a223):
        monkeypatch.setattr(module, 'source_client', client)
    report = asyncio.run(smoke.run(tmp_path))
    for key, entry in report['sources'].items():
        assert entry['state'] == 'BLOCKED'
        assert entry['real_records'] == entry['database_upserts'] == entry['query_matches'] == 0
        assert entry['law_verified'] is False
        assert report['diagnostics'][key]['http_status'] is None
        assert report['diagnostics'][key]['exception_type'] == 'ConnectorTransportError'
        assert report['diagnostics'][key]['proxy_route_rejected'] is True
        assert '127.0.0.1' not in entry['reason']


def test_optional_external_host_sample_replays_actual_adapters(monkeypatch):
    configured = os.environ.get('RU09_EIS_EVIDENCE')
    if not configured:
        pytest.skip('Optional genuine HOST TEMP capture not configured')
    path = Path(configured)
    info = smoke.external_evidence(path)
    assert info['live_proof'] is False
    payload = path.read_bytes()
    laws = smoke.law_evidence(payload)
    # This exact supplied unfiltered host sample contains 223 notices despite
    # its "44" filename; neither the filename nor search metadata proves law.
    assert info['sha256'] == 'cc4be75c896254c5be65d5eca9dfc9d767deb543f7bceb57aa49a98156b86008'
    assert info['record_links'] == 200
    assert info['law_223_links'] == 200
    assert info['law_44_links'] == 0
    for module in (a44, a223):
        calls = install_mock(monkeypatch, module, lambda request: httpx.Response(200, content=payload))
        with bounded_fetch(FetchPolicy(frozenset({'zakupki.gov.ru'}), 1, max_bytes=smoke.MAX_BYTES)):
            records = asyncio.run(adapter(module).fetch(limit=100))
        assert records and len(calls) == 1
        expected = (a44.parse_eis_feed(payload) if module is a44 else a223.parse_eis_223_feed(payload, feed_url=adapter(module).urls[0]))[:100]
        assert records == expected
        assert all(record.url in laws for record in records)
        if module is a223:
            assert all(record.independently_verified_law is None for record in records)
