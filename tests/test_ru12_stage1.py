"""Stage 1 configuration, transport and explicit cross-source identity contracts."""
import asyncio
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources import eis_rss, eis_223_rss
from app.sources.http import source_client, _policy
from app.sources.models import TenderNotice
from app.sources.ru_dedup import deduplicate


def test_catalog_opt_in_and_direct_propagation():
    settings = MonitoringSettings(False, 600, 20, 5, 15, (), None)
    assert not settings.eis_direct_enabled
    catalog = build_source_catalog(settings)
    assert 'b2b_center' not in catalog.enabled_keys
    assert 'eis_223' not in catalog.enabled_keys
    configured = replace(settings, eis_direct_enabled=True, b2b_center_enabled=True,
                         eis_223_enabled=True, eis_223_profile_feeds_enabled=True)
    catalog = build_source_catalog(configured)
    for key in ('eis', 'eis_223'):
        source = catalog.registry.get(key).source
        assert source.direct and source.for_search_terms(['test']).direct
    assert catalog.registry.get('b2b_center').display_name == 'B2B-Center'


@pytest.mark.parametrize('module,cls,builder', [
    (eis_rss, eis_rss.EisRssSource, eis_rss.build_eis_rss_url),
    (eis_223_rss, eis_223_rss.Eis223RssSource, eis_223_rss.build_eis_223_rss_url)])
def test_direct_discovery_has_bounded_policy(module, cls, builder):
    def handler(request):
        policy = _policy.get()
        assert policy.hosts == frozenset({'zakupki.gov.ru'})
        assert policy.max_requests == 20 and policy.max_bytes == 5 * 1024 * 1024
        return httpx.Response(200, content=b'<rss><channel/></rss>')

    def client(**kwargs):
        return source_client(**kwargs, transport=httpx.MockTransport(handler))

    with patch.object(module, 'source_client', client):
        assert asyncio.run(cls((builder('test'),), direct=True).fetch()) == []
    assert _policy.get() is None


def test_explicit_matching_procedure_dedup_preserves_both_notices():
    import json
    url = ('https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html'
           '?regNumber=0338200012226000019')
    eis = TenderNotice('eis', 'original', 'Synthetic', url)
    marketplace = TenderNotice('b2b_center', 'market', 'Different title',
        'https://www.b2b-center.ru/search/number/market/',
        summary=json.dumps({'upstream_url': url}))
    distinct = replace(marketplace, external_id='unlinked', summary=None)
    result, provenance = deduplicate([marketplace, distinct, eis])
    assert result == (eis, distinct)
    assert provenance == ((marketplace, eis),)
    other_law = replace(eis, source='eis_223', external_id='other-law',
        url=url.replace('/epz/order/notice/ea20/', '/223/purchase/public/purchase/'))
    assert len(deduplicate([eis, other_law])[0]) == 2


@pytest.mark.parametrize('timeout', [0, -1, float('inf'), float('nan'), 121])
@pytest.mark.parametrize('cls', [eis_rss.EisRssSource, eis_223_rss.Eis223RssSource])
def test_finite_timeout(cls, timeout):
    with pytest.raises(ValueError):
        cls((), timeout=timeout)
