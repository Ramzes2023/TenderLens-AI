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
CUSTOMER = 'ГБУЗ "Республиканская больница"'


def _settings(**updates):
    vals = dict(enabled=False, interval_seconds=600, max_items=5,
                max_notifications_per_cycle=3, request_timeout=20,
                eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False)
    vals.update(updates)
    return MonitoringSettings(**vals)


def listing(*, href="/44/procedure/ea21/" + NUMBER, org=ORGANIZER, title=TITLE):
    return (f'<html><table><tr><td>ЭА</td><td>{NUMBER}</td>'
            f'<td><a href="{href}">{title}</a><div class="label-list">СМП/СОНО 1875</div></td><td>559 936.90 RUB</td><td>{org}</td>'
            f'<td>ГБУЗ Ингушетии</td></tr></table></html>').encode()


def detail(*, number=NUMBER, title=TITLE, inn=INN, org=ORGANIZER):
    return (f'<html><h1>Сведения о закупке {number}</h1>'
            f'<main>Наименование закупки {title} Валюта Российский рубль '
            f'Сведения об организаторе закупки {org} ИНН {inn} '
            f'Контактная информация '
            f'<button>Сведения о заказчике {CUSTOMER}</button></main></html>').encode()


def test_official_row_and_independent_detail_identity():
    assert extract_regional_listing(listing()) == [(NUMBER, URL, TITLE)]
    item = verified_fabrikant_notice(detail(), number=NUMBER, url=URL, title=TITLE)
    assert item.source == SOURCE_ID
    assert item.external_id == item.tender_number == NUMBER
    assert item.region == "Республика Ингушетия"
    assert item.customer == CUSTOMER
    assert item.initial_price is None
    assert item.deadline is None


@pytest.mark.parametrize("org,href", [
    ("ДРУГОЙ РЕГИОН", "/44/procedure/ea21/" + NUMBER),
    (ORGANIZER, "https://44.fabrikant.ru.attacker.invalid/44/procedure/ea21/" + NUMBER),
    (ORGANIZER, "http://44.fabrikant.ru/44/procedure/ea21/" + NUMBER),
    (ORGANIZER, "/44/procedure/ea21/" + NUMBER + "?token=oops"),
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


def test_badges_are_not_title_and_publisher_dates_are_preserved():
    assert extract_regional_listing(listing())[0][2] == TITLE
    payload = detail().replace(b'</main>', (
        'Дата и время публикации извещения 19.10.2026 • 17:01 (МСК+00:00) '
        'Дата и время окончания срока подачи заявок 27.10.2026 • 09:00 (МСК+00:00) '
        '</main>').encode())
    item = verified_fabrikant_notice(payload, number=NUMBER, url=URL, title=TITLE)
    assert item.published_at == '19.10.2026 17:01'
    assert item.deadline == '27.10.2026 09:00'


@pytest.mark.parametrize('payload', [
    detail().replace(f'<button>Сведения о заказчике {CUSTOMER}</button>'.encode(), b''),
    detail().replace(f'ИНН {INN}'.encode(), f'ИНН {INN}0'.encode()),
    detail().replace(f'ИНН {INN}'.encode(), b'').replace(
        'Контактная информация'.encode(), f'Контактная информация ИНН {INN}'.encode()),
    detail().replace(f'Наименование закупки {TITLE}'.encode(),
                     'Наименование закупки Иной предмет'.encode()).replace(
        b'</main>', f' footer {TITLE}</main>'.encode()),
])
def test_unrelated_text_does_not_supply_missing_card_fields(payload):
    with pytest.raises(ValueError):
        verified_fabrikant_notice(payload, number=NUMBER, url=URL, title=TITLE)


def test_limit_one_fetches_only_one_detail_with_worker_request_budget(monkeypatch):
    """Offline contract: limit=1 may request only a list and one detail."""
    import app.sources.ru_ingushetia_fabrikant44 as src
    from app.sources.http import FetchPolicy, bounded_fetch
    other = '0114500000826002390'
    # Supply two correctly parsed candidates without making any external request.
    monkeypatch.setattr(src, 'extract_regional_listing', lambda payload: [
        (NUMBER, URL, TITLE), (other, URL.replace(NUMBER, other), TITLE)])
    calls = []
    class Client:
        async def get(self, url):
            calls.append(url)
            assert len(calls) <= 2
            return SimpleNamespace(content=listing() if url == LIST_URL else detail(),
                                   headers={'content-type': 'text/html'}, raise_for_status=lambda: None)
    @asynccontextmanager
    async def client(**kwargs):
        yield Client()
    monkeypatch.setattr(src, 'source_client', client)
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 2)):
        assert len(asyncio.run(IngushetiaFabrikant44Source().fetch(1))) == 1
    assert calls == [LIST_URL, URL]
