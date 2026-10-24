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
from app.sources.ru_ingushetia_fabrikant44 import (
    IngushetiaFabrikant44Source, SOURCE_ID, HOST, LIST_URL, ORGANIZER, INN,
    extract_regional_listing, verified_fabrikant_notice, DETAIL_MIRROR_HOST,
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
    assert reg.homepage_url.startswith('https://44.fabrikant.ru/44/catalog/procedure/published')
    assert HOSTS[SOURCE_ID] == frozenset({HOST, DETAIL_MIRROR_HOST})



def test_real_mirror_cannot_inflate_official_eis_original_count():
    mirror = verified_fabrikant_notice(detail(), number=NUMBER, url=URL, title=TITLE)
    eis = TenderNotice(
        source="eis", external_id="eis-local", tender_number=NUMBER,
        title=TITLE, url="https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=" + NUMBER,
    )
    assert original_notice_key(mirror) == original_notice_key(eis) == ("eis_44", NUMBER)


def test_hostile_script_id_does_not_prove_a_real_visible_publisher_card():
    with pytest.raises(ValueError):
        verified_fabrikant_notice(
            (f"<html><script>Сведения о закупке {NUMBER} {INN}</script><h1>Login</h1></html>").encode(),
            number=NUMBER, url=URL, title=TITLE,
        )


def test_source_disabled_protects_scoring_selection():
    from app.scoring.runs import ScoringInputError, validate_configuration
    assert validate_configuration([SOURCE_ID], 3)["sources"] == [SOURCE_ID]
    assert SOURCE_ID not in build_source_catalog(_settings()).enabled_keys
