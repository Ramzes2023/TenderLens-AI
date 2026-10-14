"""Offline contracts for the opt-in RU integrations on the Phase 24 catalog.

These tests do not establish live acquisition or authenticated AI search.
"""
import asyncio
import ssl
from unittest.mock import patch

import httpx
import pytest

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.b2b_center import B2BCenterSource, parse_b2b_center_listing
from app.sources.eis_rss import (
    EIS_EXTENDED_RSS_URL, EisRssSource, SourceError,
    eis_tls_verify, verify_eis_feed_law,
)
from app.sources.eis_223_rss import Eis223RssSource


def _settings(**kwargs):
    values = dict(
        enabled=False, interval_seconds=600, max_items=20,
        max_notifications_per_cycle=5, request_timeout=15,
        eis_rss_urls=(), ca_bundle_file=None,
    )
    values.update(kwargs)
    return MonitoringSettings(**values)


def test_defaults_leave_new_live_connectors_disabled():
    catalog = build_source_catalog(_settings())
    assert 'eis_223' not in catalog.registry.keys()
    assert 'b2b_center' not in catalog.registry.keys()


def test_opt_in_russian_sources_preserve_international_registry():
    baseline = build_source_catalog(_settings())
    configured = build_source_catalog(_settings(
        eis_223_enabled=True,
        eis_223_rss_urls=(EIS_EXTENDED_RSS_URL + '?fz223=on',),
        b2b_center_enabled=True,
        eis_direct_enabled=True,
    ))
    assert {'eis_223', 'b2b_center'} <= set(configured.enabled_keys)
    assert set(baseline.registry.keys()) <= set(configured.registry.keys())
    assert isinstance(configured.registry.get('eis_223').source, Eis223RssSource)
    assert isinstance(configured.registry.get('b2b_center').source, B2BCenterSource)
    assert configured.registry.get('eis_223').source.direct is True
    assert configured.registry.get('eis').source.direct is True


def test_eis_windows_trust_rejects_unsafe_configuration():
    with pytest.raises(ValueError):
        eis_tls_verify(direct=False, system_trust=True, ca_bundle_file=None)
    with pytest.raises(ValueError):
        eis_tls_verify(direct=True, system_trust=True, ca_bundle_file='unsafe.crt')
    assert eis_tls_verify(direct=True, system_trust=False, ca_bundle_file=None) is True


def _item(law):
    route = ('/epz/order/notice/ea44/view/common-info.html' if law == '44'
             else '/223/purchase/public/purchase/info/common-info.html')
    return (
        '<item><title>test</title>'
        '<link>https://zakupki.gov.ru' + route +
        '?regNumber=1234567890123456789</link>'
        '<description>Найденный результат: Размещение выполняется по: ' +
        law + '-ФЗ</description></item>'
    )


def test_whole_feed_law_gate_rejects_mixed_and_wrong_law():
    good = ('<rss><channel>' + _item('44') + '</channel></rss>').encode()
    verify_eis_feed_law(good, '44-FZ')
    with pytest.raises(SourceError):
        verify_eis_feed_law(good, '223-FZ')
    mixed = ('<rss><channel>' + _item('44') + _item('223')
             + '</channel></rss>').encode()
    with pytest.raises(SourceError):
        verify_eis_feed_law(mixed, '44-FZ')
    with pytest.raises(SourceError):
        verify_eis_feed_law(mixed, '223-FZ')


def test_b2b_rejects_non_notice_html_without_network():
    for body in (b'', b'<html><form>Login required</form></html>',
                 b'<html>Captcha verification</html>'):
        with pytest.raises(SourceError):
            parse_b2b_center_listing(body)


def test_russian_notices_survive_sqlite_and_snapshot_keyword_search(tmp_path):
    """Actual offline storage and search; subclass metadata must survive reads."""
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    from app.sources.b2b_center import B2BCenterNotice
    from app.sources.eis_223_rss import Eis223Notice
    from app.sources.models import TenderNotice
    from app.sources.opportunities import OpportunityRepository
    from app.sources.snapshots import snapshot_catalog

    catalog = build_source_catalog(_settings(
        eis_rss_urls=(EIS_EXTENDED_RSS_URL + '?fz44=on',),
        eis_223_enabled=True,
        eis_223_rss_urls=(EIS_EXTENDED_RSS_URL + '?fz223=on',),
        b2b_center_enabled=True,
        profile_feeds_enabled=False,
    ))
    db = Database(DatabaseSettings('ru-offline-test', tmp_path / 'ru_sources.sqlite'))
    repo = OpportunityRepository(db)
    repo.initialize()
    notices = (
        TenderNotice(
            source='eis', external_id='test-44-id-001', title='Тестовая закупка 44',
            url='https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=12345678901',
        ),
        Eis223Notice(
            source='eis_223', external_id='test-223-id-001',
            title='Тестовая закупка 223',
            url='https://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html?regNumber=12345678901',
            observed_law='223-FZ', feed_url=EIS_EXTENDED_RSS_URL + '?fz223=on',
            raw_guid='test-223-id-001',
        ),
        B2BCenterNotice(
            source='b2b_center', external_id='test-b2b-id-001',
            title='Тестовая закупка B2B-Center',
            url='https://www.b2b-center.ru/search/number/test-b2b-id-001/',
            upstream_url='https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=12345678901',
            upstream_host='zakupki.gov.ru', origin='aggregated',
        ),
    )
    try:
        for notice in notices:
            assert repo.upsert(notice, f'connector-sync-v1:{notice.source}:adapter-r1')
            assert not repo.upsert(notice, f'connector-sync-v1:{notice.source}:adapter-r1')
        snapshot = snapshot_catalog(catalog, repo)
        for original in notices:
            result = asyncio.run(snapshot.fetch(
                source_keys=(original.source,),
                search_terms=(original.external_id,),
                limit_per_source=10,
            ))
            assert not result.failures
            assert len(result.notices) == 1
            restored = result.notices[0]
            assert restored.identity == original.identity
            assert restored.url == original.url
            assert type(restored) is type(original)
            if isinstance(original, Eis223Notice):
                assert restored.observed_law == '223-FZ'
                assert restored.feed_url == original.feed_url
            if isinstance(original, B2BCenterNotice):
                assert restored.upstream_url == original.upstream_url
                assert restored.origin == 'aggregated'
    finally:
        db.close()
