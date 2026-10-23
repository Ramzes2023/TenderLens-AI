"""Synthetic Chechnya 44-FZ marketplace contracts, never live proof."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.sources.ru_chechnya_fabrikant44 import (
    ChechnyaFabrikant44Source, HOST, LIST_URL, INN, ORGANIZER, REGION,
    SOURCE_ID, extract_regional_listing, verified_fabrikant_notice,
)

NUMBER = "0194200000526005514"
URL = f"https://{HOST}/44/procedure/ea21/{NUMBER}"
TITLE = "Строительство здания общественного назначения"


def listing(*, number=NUMBER, title=TITLE, org=ORGANIZER, href=None):
    link = href or f"/44/procedure/ea21/{number}"
    return (f'<html><table><tr><td>ЭА</td><td>{number}</td>'
            f'<td><a href="{link}">{title}</a></td>'
            f'<td>2000 RUB</td><td>{org}</td>'
            f'<td>Заказчик Чеченской Республики</td></tr></table></html>').encode()


def detail(*, number=NUMBER, title=TITLE, inn=INN, org=ORGANIZER):
    return (f'<html><body><h1>Сведения о закупке {number}</h1>'
            f'<main>Наименование закупки {title} '
            f'Сведения об организаторе закупки {org} ИНН {inn}</main>'
            '</body></html>').encode()


def test_only_publisher_original_region_and_organizer_inn():
    assert extract_regional_listing(listing()) == [(NUMBER, URL, TITLE)]
    notice = verified_fabrikant_notice(detail(), number=NUMBER, url=URL, title=TITLE)
    assert notice.source == SOURCE_ID
    assert notice.region == REGION == "Чеченская Республика"
    assert notice.tender_number == NUMBER and notice.external_id == NUMBER
    assert notice.customer == ORGANIZER
    assert notice.initial_price is None and notice.deadline is None


def test_catalog_research_is_not_implicitly_registered_or_production_enabled():
    from app.sources.catalog import build_source_catalog
    from app.monitoring.config import MonitoringSettings
    cfg = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=5,
        max_notifications_per_cycle=3, request_timeout=20,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
    )
    assert SOURCE_ID not in build_source_catalog(cfg).enabled_keys


@pytest.mark.parametrize("org,link", [
    ("Another region committee", "/44/procedure/ea21/" + NUMBER),
    (ORGANIZER, "https://44.fabrikant.ru.evil.invalid/44/procedure/ea21/" + NUMBER),
    (ORGANIZER, "http://44.fabrikant.ru/44/procedure/ea21/" + NUMBER),
    (ORGANIZER, "/44/procedure/ea21/" + NUMBER + "?token=secret"),
    (ORGANIZER, "/44/procedure/ea21/" + NUMBER + "?&backurl=ok&private=x"),
])
def test_official_listing_rejects_wrong_buyer_and_unapproved_navigation(org, link):
    with pytest.raises(ValueError):
        extract_regional_listing(listing(org=org, href=link))


@pytest.mark.parametrize("payload", [
    detail(number="0194200000526005515"),
    detail(title="Несовпадающее название закупки"),
    detail(inn="0000000000"),
    detail(org="Несоответствующий государственный заказчик"),
    b"<html><form>Account login required</form></html>",
])
def test_independent_detail_rejects_wrong_original(payload):
    with pytest.raises(ValueError):
        verified_fabrikant_notice(payload, number=NUMBER, url=URL, title=TITLE)


def test_bounded_official_only_live_adapter_contract_offline(monkeypatch):
    seen = []
    class FakeClient:
        async def get(self, url):
            seen.append(url)
            return SimpleNamespace(
                content=listing() if url == LIST_URL else detail(),
                headers={"content-type": "text/html"},
                raise_for_status=lambda: None,
            )

    @asynccontextmanager
    async def fake_source(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield FakeClient()

    import app.sources.ru_chechnya_fabrikant44 as mod
    monkeypatch.setattr(mod, "source_client", fake_source)
    notices = asyncio.run(ChechnyaFabrikant44Source().fetch(limit=1))
    assert [n.tender_number for n in notices] == [NUMBER]
    assert seen == [LIST_URL, URL]


def test_operator_disabled_default_and_real_firstparty_source_explicit_opt_in():
    from dataclasses import replace
    from app.sources.ru_cycle import approved_ru_keys
    from app.sources.ingestion import HOSTS
    from app.scoring.runs import validate_configuration, ScoringInputError
    from app.monitoring.config import MonitoringSettings
    from app.sources.catalog import build_source_catalog

    base = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=3,
        max_notifications_per_cycle=2, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
    )
    disabled = build_source_catalog(base)
    assert SOURCE_ID not in disabled.enabled_keys
    with pytest.raises(ValueError, match="No operator-approved"):
        approved_ru_keys(disabled)

    enabled = build_source_catalog(replace(base, ru_chechnya_fabrikant44_enabled=True))
    assert SOURCE_ID in enabled.enabled_keys
    assert approved_ru_keys(enabled) == (SOURCE_ID,)
    assert HOSTS[SOURCE_ID] == frozenset({"44.fabrikant.ru", "soap4.fabrikant.ru"})
    assert enabled.registry.get(SOURCE_ID).metadata.official is False
    assert validate_configuration([SOURCE_ID], 3)["sources"] == [SOURCE_ID]


def test_chechnya_eis_native_number_stays_same_and_not_a_unique_eis_publisher():
    data = verified_fabrikant_notice(detail(), number=NUMBER, url=URL, title=TITLE)
    assert len(data.external_id) == 19
    assert data.tender_number == data.external_id
    assert data.source == SOURCE_ID
    assert data.customer == ORGANIZER
    assert data.initial_price is None
    assert data.region == REGION
