"""Synthetic contracts only: NEVER interpret as genuine live Ingushetia notice proof."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import HOSTS
from app.sources.models import TenderNotice
from app.sources.ru_notice_identity import original_notice_key
from app.sources.ru_dedup import deduplicate
from app.sources.ru_ingushetia_fabrikant44 import (
    IngushetiaFabrikant44Source, SOURCE_ID, HOST, LIST_URL, ORGANIZER, INN,
    extract_regional_listing, verified_fabrikant_notice,
)

NUMBER = "0114500000826002358"
URL = "https://" + HOST + "/44/procedure/ea21/" + NUMBER
TITLE = "Поставка лекарственных средств"


def _settings(**updates):
    vals = dict(enabled=False, interval_seconds=600, max_items=5,
                max_notifications_per_cycle=3, request_timeout=20,
                eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False)
    vals.update(updates)
    return MonitoringSettings(**vals)


def listing(*, href="/44/procedure/ea21/" + NUMBER, org=ORGANIZER, title=TITLE):
    return (f'<html><table><tr><td>ЭА</td><td><a href="{href}">{NUMBER}</a></td>'
            f'<td>{title}</td><td>559 936.90 RUB</td><td>{org}</td>'
            f'<td>ГБУЗ Ингушетии</td></tr></table></html>').encode()


def detail(*, number=NUMBER, title=TITLE, inn=INN, org=ORGANIZER):
    return (f'<html><h1>Сведения о закупке {number}</h1>'
            f'<main>Наименование закупки {title} '
            f'Сведения об организаторе закупки {org} ИНН {inn}</main></html>').encode()


def test_official_row_and_independent_detail_identity():
    assert extract_regional_listing(listing()) == [(NUMBER, URL, TITLE)]
    item = verified_fabrikant_notice(detail(), number=NUMBER, url=URL, title=TITLE)
    assert item.source == SOURCE_ID
    assert item.external_id == item.tender_number == NUMBER
    assert item.region == "Республика Ингушетия"
    assert item.customer == ORGANIZER
    assert item.initial_price is None
    assert item.deadline is None


def test_public_organizer_filter_is_newest_first_not_procurement_text_search():
    from urllib.parse import parse_qs, urlsplit
    parsed = urlsplit(LIST_URL)
    assert parsed.path == "/44/catalog/procedure/published"
    assert parse_qs(parsed.query) == {
        "placer_search_str": [INN], "order": ["publication_datetime"], "dir": ["desc"],
    }


def test_title_anchor_excludes_real_catalog_preference_badges():
    html = listing().decode().replace(
        f"<td>{TITLE}</td>",
        f'<td><a href="/44/procedure/ea21/{NUMBER}?&backurl=abc">{TITLE}</a>'
        '<div class="label-list"><div>СМП/СОНО</div><div>1875</div></div></td>',
    ).encode()
    assert extract_regional_listing(html) == [(NUMBER, URL, TITLE)]


@pytest.mark.parametrize("org,href", [
    ("ДРУГОЙ РЕГИОН", "/44/procedure/ea21/" + NUMBER),
    (ORGANIZER, "https://44.fabrikant.ru.attacker.invalid/44/procedure/ea21/" + NUMBER),
    (ORGANIZER, "http://44.fabrikant.ru/44/procedure/ea21/" + NUMBER),
    (ORGANIZER, "/44/procedure/ea21/" + NUMBER + "?token=oops"),
    (ORGANIZER, "/44/procedure/ea21/" + NUMBER + "?&backurl=safe&token=oops"),
    (ORGANIZER, "/44/procedure/ea21/" + NUMBER + "?&backurl="),
    (ORGANIZER, "/44/procedure/ea21/123456789"),
])
def test_fails_closed_on_other_buyers_or_unsafe_link(org, href):
    with pytest.raises(ValueError):
        extract_regional_listing(listing(org=org, href=href))


@pytest.mark.parametrize("html", [
    detail(number="0114500000826002359"),
    detail(title="Другой предмет закупки"),
    detail(org="Сторонний комитет"),
    detail(inn="0123456789"),
    b"<html><form>Sign in</form></html>",
])
def test_spoofed_or_unverified_original_rejected(html):
    with pytest.raises(ValueError):
        verified_fabrikant_notice(html, number=NUMBER, url=URL, title=TITLE)


def test_enabled_only_by_explicit_opt_in_and_official_host_only():
    assert SOURCE_ID not in build_source_catalog(_settings()).registry.keys()
    c = build_source_catalog(_settings(ru_ingushetia_fabrikant44_enabled=True))
    assert SOURCE_ID in c.enabled_keys
    reg = c.registry.get(SOURCE_ID)
    assert isinstance(reg.source, IngushetiaFabrikant44Source)
    assert reg.source.name == SOURCE_ID
    assert reg.homepage_url == LIST_URL
    assert HOSTS[SOURCE_ID] == frozenset({HOST})


def test_cross_eis_original_dedup_is_not_double_user_alert():
    mirror = verified_fabrikant_notice(detail(), number=NUMBER, url=URL, title=TITLE)
    generic = TenderNotice(source="eis", external_id="eis-local-123",
                           tender_number=NUMBER, title=TITLE,
                           url="https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber="+NUMBER)
    assert original_notice_key(mirror) == original_notice_key(generic) == ("eis_44", NUMBER)
    unique, dupe = deduplicate([generic, mirror])
    assert len(unique) == 1 and unique[0].source == "eis"
    assert len(dupe) == 1


def test_mocked_vendor_client_is_not_live_proof(monkeypatch):
    calls = []
    class FakeClient:
        async def get(self, url):
            calls.append(url)
            payload = listing() if url == LIST_URL else detail()
            return SimpleNamespace(content=payload, headers={"content-type": "text/html"},
                                   raise_for_status=lambda: None)

    @asynccontextmanager
    async def fake_source_client(**kw):
        assert kw["follow_redirects"] is False
        assert kw["trust_env"] is False
        yield FakeClient()

    import app.sources.ru_ingushetia_fabrikant44 as src
    monkeypatch.setattr(src, "source_client", fake_source_client)
    result = asyncio.run(IngushetiaFabrikant44Source().fetch(limit=3))
    assert len(result) == 1 and result[0].tender_number == NUMBER
    assert calls == [LIST_URL, URL]


def test_one_stale_detail_never_loses_two_independently_verified_rows(monkeypatch):
    """Synthetic partial outage: only verified originals survive; no fake success."""
    import app.sources.ru_ingushetia_fabrikant44 as mod
    from app.sources.http import ConnectorTransportError

    numbers = ("0114500000826002358", "0114500000826002359", "0114500000826002360")
    titles = ("Поставка лекарств", "Поставка оборудования", "Ремонт здания")
    rows = []
    for number, title in zip(numbers, titles):
        rows.append(
            f'<tr><td>ЭА</td><td>{number}</td>'
            f'<td><a href="/44/procedure/ea21/{number}?&backurl=safe">{title}</a></td>'
            f'<td>100.00 RUB</td><td>{ORGANIZER}</td><td>Больница</td></tr>'
        )
    payload = ("<html><table>" + "".join(rows) + "</table></html>").encode()
    calls = []

    class Client:
        async def get(self, url):
            calls.append(url)
            if url == LIST_URL:
                body = payload
            elif url.endswith(numbers[2]):
                raise ConnectorTransportError(retryable=True)
            else:
                index = next(i for i, number in enumerate(numbers) if url.endswith(number))
                body = detail(number=numbers[index], title=titles[index])
            return SimpleNamespace(
                content=body, headers={"content-type": "text/html"},
                raise_for_status=lambda: None,
            )

    @asynccontextmanager
    async def fake_client(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        yield Client()

    monkeypatch.setattr(mod, "source_client", fake_client)
    verified = asyncio.run(IngushetiaFabrikant44Source().fetch(limit=3))
    assert [n.tender_number for n in verified] == list(numbers[:2])
    assert len(calls) == 4


def test_no_verified_card_is_never_reported_as_success(monkeypatch):
    import app.sources.ru_ingushetia_fabrikant44 as mod
    from app.sources.http import ConnectorTransportError

    class Client:
        async def get(self, url):
            if url == LIST_URL:
                return SimpleNamespace(
                    content=listing(),
                    headers={"content-type": "text/html"},
                    raise_for_status=lambda: None,
                )
            raise ConnectorTransportError(retryable=True)

    @asynccontextmanager
    async def fake_client(**kwargs):
        yield Client()

    monkeypatch.setattr(mod, "source_client", fake_client)
    with pytest.raises(ValueError, match="No independently verified regional original cards"):
        asyncio.run(IngushetiaFabrikant44Source().fetch(limit=3))


def test_transient_listing_failure_is_retried_once_only(monkeypatch):
    """Synthetic connection loss, never a substitute for live HTTP proof."""
    import app.sources.ru_ingushetia_fabrikant44 as mod
    from app.sources.http import ConnectorTransportError

    seen = []

    class Client:
        async def get(self, url):
            seen.append(url)
            if url == LIST_URL and seen.count(LIST_URL) == 1:
                raise ConnectorTransportError(retryable=True)
            return SimpleNamespace(
                content=listing() if url == LIST_URL else detail(),
                headers={"content-type": "text/html"},
                raise_for_status=lambda: None,
            )

    @asynccontextmanager
    async def fake_client(**kwargs):
        yield Client()

    async def no_delay(value):
        assert value == 0.75

    monkeypatch.setattr(mod, "source_client", fake_client)
    monkeypatch.setattr(mod.asyncio, "sleep", no_delay)
    result = asyncio.run(IngushetiaFabrikant44Source().fetch(limit=1))
    assert [item.tender_number for item in result] == [NUMBER]
    assert seen == [LIST_URL, LIST_URL, URL]


def test_permanent_listing_failure_does_not_trigger_retry(monkeypatch):
    import app.sources.ru_ingushetia_fabrikant44 as mod
    from app.sources.http import ConnectorTransportError

    seen = []

    class Client:
        async def get(self, url):
            seen.append(url)
            raise ConnectorTransportError(retryable=False)

    @asynccontextmanager
    async def fake_client(**kwargs):
        yield Client()

    monkeypatch.setattr(mod, "source_client", fake_client)
    with pytest.raises(ConnectorTransportError):
        asyncio.run(IngushetiaFabrikant44Source().fetch(limit=2))
    assert seen == [LIST_URL]
