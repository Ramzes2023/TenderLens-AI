"""Synthetic offline law tests; never live evidence."""
import asyncio
from unittest.mock import patch

import httpx
import pytest

from app.sources import eis_rss as a44, eis_223_rss as a223
from app.sources.http import source_client, bounded_fetch, FetchPolicy


def item(law, *, label=None, host='zakupki.gov.ru'):
    path = ('/epz/order/notice/ea44/view/common-info.html' if law == '44'
            else '/223/purchase/public/purchase/info/common-info.html')
    return (f'<item><guid>SYNTHETIC-{law}</guid><title>Test</title>'
            f'<link>https://{host}{path}?regNumber=1234567890123456789</link>'
            f'<description>Найденный результат: Размещение выполняется по: '
            f'{label or law}-ФЗ</description></item>')


def feed(*items):
    return ('<rss><channel>' + ''.join(items) + '</channel></rss>').encode()


@pytest.mark.parametrize('law', ['44', '223'])
def test_matching_route_and_result_label(law):
    a44.verify_eis_feed_law(feed(item(law)), law + '-FZ')


@pytest.mark.parametrize('law', ['44', '223'])
@pytest.mark.parametrize('kind', ['other', 'mixed', 'late', 'conflict', 'unknown', 'host', 'preamble'])
def test_whole_feed_fail_closed(law, kind):
    other = '223' if law == '44' else '44'
    payload = {
        'other': feed(item(other)),
        'mixed': feed(item(law), item(other)),
        'late': feed(*([item(law)] * 25), item(other)),
        'conflict': feed(item(law, label=other)),
        'unknown': feed(item(law, label='999')),
        'host': feed(item(law, host='127.0.0.1')),
        'preamble': feed(item(law)).replace('Найденный результат:'.encode(),
            ('Размещение выполняется по: ' + law + '-ФЗ Найденный результат:').encode()
        ).replace(('Найденный результат: Размещение выполняется по: ' + law + '-ФЗ').encode(),
                  'Найденный результат: нет метки'.encode()),
    }[kind]
    with pytest.raises(a44.SourceError):
        a44.verify_eis_feed_law(payload, law + '-FZ')


@pytest.mark.parametrize('module,law', [(a44, '44'), (a223, '223')])
def test_adapter_checks_late_other_law_before_limit(module, law):
    other = '223' if law == '44' else '44'
    payload = feed(*([item(law)] * 25), item(other))
    source = (a44.EisRssSource((a44.build_eis_rss_url('test'),), direct=True)
              if law == '44' else a223.Eis223RssSource((a223.build_eis_223_rss_url('test'),), direct=True))
    def client(**kwargs):
        return source_client(**kwargs, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=payload)))
    async def run():
        with bounded_fetch(FetchPolicy(frozenset({'zakupki.gov.ru'}), 1)):
            with patch.object(module, 'source_client', client):
                with pytest.raises(a44.SourceError):
                    await source.fetch(limit=1)
    asyncio.run(run())


@pytest.mark.parametrize('payload', [b'<!DOCTYPE rss><rss/>', b'<html/>', b'<rss>', b'x' * (5 * 1024 * 1024 + 1)], ids=['doctype', 'html', 'incomplete-rss', 'oversized-xml'])
def test_invalid_payload(payload):
    with pytest.raises(a44.SourceError):
        a44.verify_eis_feed_law(payload, '223-FZ')


@pytest.mark.parametrize('direct', [False, True])
def test_only_exact_selected_mock_route_has_legacy_semantics(direct):
    from app.sources.http import _RejectedProxyTransport

    class MockSubclass(httpx.MockTransport):
        pass

    class Routes:
        def __init__(self, route):
            self.route = route

        def _transport_for_url(self, url):
            assert url.host == 'zakupki.gov.ru'
            return self.route

    url = a223.build_eis_223_rss_url('test')
    mock = httpx.MockTransport(lambda request: httpx.Response(200))
    assert a44.requires_eis_law_validation(Routes(mock), url, direct=direct) is direct
    for route in (None, _RejectedProxyTransport(), MockSubclass(mock.handler)):
        assert a44.requires_eis_law_validation(Routes(route), url, direct=direct)
    assert a44.requires_eis_law_validation(object(), url, direct=direct)


@pytest.mark.parametrize('direct', [False, True])
def test_legacy_223_fixture_is_unverified_and_direct_requires_evidence(direct):
    payload = feed('<item><guid>fixture</guid><title>Test</title>'
                   '<link>https://zakupki.gov.ru/notice/32616463738</link>'
                   '<description>Размещение выполняется по: 223-ФЗ</description></item>')
    def client(**kwargs):
        return source_client(**kwargs, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=payload)))

    async def run():
        with patch.object(a223, 'source_client', client):
            source = a223.Eis223RssSource((a223.build_eis_223_rss_url('test'),), direct=direct)
            if direct:
                with pytest.raises(a44.SourceError):
                    await source.fetch()
            else:
                notice, = await source.fetch()
                assert notice.identity == ('eis_223', 'fixture')
                assert notice.observed_law == '223-FZ'
                assert notice.independently_verified_law is None
    asyncio.run(run())


@pytest.mark.parametrize('module,law', [(a44, '44'), (a223, '223')])
@pytest.mark.parametrize('direct', [False, True])
def test_wrong_law_mock_preserves_parser_contract_without_law_proof(module, law, direct):
    other = '223' if law == '44' else '44'
    payload = feed(item(other))
    builder = a44.build_eis_rss_url if law == '44' else a223.build_eis_223_rss_url
    cls = a44.EisRssSource if law == '44' else a223.Eis223RssSource

    def client(**kwargs):
        return source_client(**kwargs, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=payload)))

    async def run():
        with bounded_fetch(FetchPolicy(frozenset({'zakupki.gov.ru'}), 1)):
            with patch.object(module, 'source_client', client):
                if direct:
                    with pytest.raises(a44.SourceError):
                        await cls((builder('test'),), direct=True).fetch()
                else:
                    notice, = await cls((builder('test'),)).fetch()
                    # A source namespace is not a law label or live evidence.
                    assert notice.source == ('eis' if law == '44' else 'eis_223')
                    assert getattr(notice, 'independently_verified_law', None) is None
                    if law == '223':
                        assert notice.observed_law == '44-FZ'
                    with pytest.raises(a44.SourceError):
                        a44.verify_eis_feed_law(payload, law + '-FZ')
    asyncio.run(run())
