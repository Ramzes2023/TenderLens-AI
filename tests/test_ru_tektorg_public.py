"""Offline TEK-Torg public 223-FZ source contract; all fixtures synthetic."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.tektorg_public_html import (
    HOST, LIST_URL, SOURCE_ID, TekTorgPublicSource,
    parse_public_listing, validate_public_detail,
)
from app.scoring.runs import ScoringInputError, validate_configuration


def listing(title="Поставка стали", link="/223-fz/procedures/20000521"):
    return (f"<html><a href='{link}'><span>{title}</span></a></html>").encode()


def detail(title="Поставка стали", identity="20000521"):
    return (f"<html><head><title>Извещение о процедуре {identity}</title></head>"
            f"<body><p>Номер процедуры {identity}</p>"
            f"<h1><span>{title}</span></h1></body></html>").encode()


def settings(**changes):
    base = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=10,
        max_notifications_per_cycle=5, request_timeout=15,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
    )
    return replace(base, **changes)


def test_default_disabled_and_source_scoring_selection():
    assert SOURCE_ID not in build_source_catalog(settings()).enabled_keys
    catalog = build_source_catalog(settings(tektorg_public_enabled=True))
    assert SOURCE_ID in catalog.enabled_keys
    assert catalog.registry.get(SOURCE_ID).metadata.official is False
    assert validate_configuration([SOURCE_ID], 10)["sources"] == [SOURCE_ID]


def test_public_listing_normalizes_id_and_title_with_real_path_shape():
    cards = parse_public_listing(listing())
    assert cards == [("20000521", f"https://{HOST}/223-fz/procedures/20000521",
                      "Поставка стали")]
    validate_public_detail(detail(), identity="20000521", title="Поставка стали")


@pytest.mark.parametrize("html", [
    b"",
    b"<html>No cards</html>",
    listing(link="https://www.tektorg.ru.evil.invalid/223-fz/procedures/20000521"),
    listing(link="https://www.tektorg.ru/223-fz/procedures/20000521?token=x"),
    listing(link="https://www.tektorg.ru/223-fz/procedures/20000521#fragment"),
    listing(link="http://www.tektorg.ru/223-fz/procedures/20000521"),
    listing(title=" "),
    listing(title="<script>alert(1)</script>"),
])
def test_incomplete_or_malformed_listing_fails_closed(html):
    with pytest.raises(ValueError):
        parse_public_listing(html)


def test_detail_requires_same_title_and_identity():
    for body in (detail(title="Другой тендер"),
                 detail(identity="20000522"),
                 "<html><h1>Поставка стали</h1></html>".encode("utf-8")):
        with pytest.raises(ValueError):
            validate_public_detail(body, identity="20000521", title="Поставка стали")


def test_conflicting_duplicate_identity_fails_closed():
    body = listing() + listing(title="Иной товар")
    with pytest.raises(ValueError):
        parse_public_listing(body, limit=3)


def test_real_adapter_public_request_contract_offline(monkeypatch):
    seen = []
    class FakeClient:
        async def get(self, url):
            seen.append(url)
            content = listing() if url == LIST_URL else detail()
            return SimpleNamespace(
                content=content,
                headers={"content-type": "text/html; charset=utf-8"},
                raise_for_status=lambda: None,
            )
    @asynccontextmanager
    async def fake_source_client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        assert kwargs["timeout"] == 15
        assert kwargs["headers"]["Accept"] == "text/html"
        assert kwargs["headers"]["User-Agent"] == "Mozilla/5.0"
        yield FakeClient()
    import app.sources.tektorg_public_html as module
    monkeypatch.setattr(module, "source_client", fake_source_client)
    notices = asyncio.run(TekTorgPublicSource(timeout=15).fetch(1))
    assert seen == [LIST_URL, f"https://{HOST}/223-fz/procedures/20000521"]
    assert len(notices) == 1
    assert notices[0].identity == (SOURCE_ID, "20000521")
    assert notices[0].title == "Поставка стали"


@pytest.mark.parametrize("limit", [0, True, 101, "5"])
def test_invalid_limit_rejected(limit):
    with pytest.raises(ValueError):
        asyncio.run(TekTorgPublicSource().fetch(limit))

def test_drops_stale_public_detail_but_keeps_independently_verified_notice(monkeypatch):
    first = "https://www.tektorg.ru/223-fz/procedures/20000521"
    second = "https://www.tektorg.ru/223-fz/procedures/20000522"
    pair = listing() + listing(title="Поставка кабелей", link="/223-fz/procedures/20000522")

    class FakeClient:
        async def get(self, url):
            if url == LIST_URL:
                body = pair
            elif url == first:
                body = detail(title="Некорректная карточка", identity="20000521")
            elif url == second:
                body = detail(title="Поставка кабелей", identity="20000522")
            else:
                raise AssertionError("Unexpected URL")
            return SimpleNamespace(
                content=body, headers={"content-type": "text/html"},
                raise_for_status=lambda: None,
            )

    @asynccontextmanager
    async def client(**kwargs):
        yield FakeClient()

    import app.sources.tektorg_public_html as module
    monkeypatch.setattr(module, "source_client", client)
    notices = asyncio.run(TekTorgPublicSource(timeout=15).fetch(2))
    assert [n.external_id for n in notices] == ["20000522"]


def test_all_stale_tektorg_details_fail_closed(monkeypatch):
    class FakeClient:
        async def get(self, url):
            return SimpleNamespace(
                content=listing() if url == LIST_URL else detail(title="Не совпадает"),
                headers={"content-type": "text/html"},
                raise_for_status=lambda: None,
            )
    @asynccontextmanager
    async def client(**kwargs):
        yield FakeClient()
    import app.sources.tektorg_public_html as module
    monkeypatch.setattr(module, "source_client", client)
    with pytest.raises(ValueError, match="No independently verified"):
        asyncio.run(TekTorgPublicSource(timeout=15).fetch(1))


@pytest.mark.parametrize("payload", [
    b"<html><head><title>20000521</title></head><body><h1>Real title</h1></body></html>",
    b"<html><body><script>window.proc='20000521'</script><h1>Real title</h1></body></html>",
    b"<html><body><style>.id:after{content:'20000521'}</style><h1>Real title</h1></body></html>",
    b"<html><body><template>20000521</template><h1>Real title</h1></body></html>",
    b"<html><body><p>200005219</p><h1>Real title</h1></body></html>",
    b"<html><body><p>120000521</p><h1>Real title</h1></body></html>",
])
def test_hidden_or_embedded_native_detail_id_is_not_firstparty_identity(payload):
    with pytest.raises(ValueError, match="title/identity mismatch"):
        validate_public_detail(payload, identity="20000521", title="Real title")


def test_valid_native_id_in_real_visible_detail_with_unrelated_head_number():
    payload = (
        b"<html><head><title>Different page metadata</title></head>"
        b"<body><p>Official procurement number 20000521</p>"
        b"<h1>Real title</h1></body></html>"
    )
    validate_public_detail(payload, identity="20000521", title="Real title")


def test_hidden_markup_inside_heading_never_evidences_native_id():
    payload = (
        b"<html><head><title>20000521</title></head><body>"
        b"<h1>Real title<script>20000521</script></h1></body></html>"
    )
    with pytest.raises(ValueError, match="title/identity mismatch"):
        validate_public_detail(payload, identity="20000521", title="Real title")


def test_publisher_native_zp_procurement_id_is_independently_visible_on_original_detail():
    # Official TEK-Torg 223-FZ cards show /223-fz/procedures/<internal ID>
    # and a *different* human-readable procurement number such as ZP409589.
    # This is a synthetic reproduction of the publisher-visible structure,
    # not a fresh network success claim.
    actual = (
        "<html><head><title>Сайт закупок</title></head><body>"
        "<nav>223-ФЗ Извещение о процедуре ЗП409589</nav>"
        "<section><p>Общие сведения</p><p>№ ЗП409589</p></section>"
        "<h1>Поставка стали</h1></body></html>"
    ).encode("utf-8")
    result = validate_public_detail(actual, identity="20000521", title="Поставка стали")
    assert result == "ЗП409589"


@pytest.mark.parametrize("invalid", [
    # Published ID occurs only in metadata or scripted text.
    "<head><title>Извещение о процедуре ЗП409589</title></head><body>"
    "<p>№ ЗП409589</p><h1>Поставка стали</h1></body>",
    "<body><script>Извещение о процедуре ЗП409589</script>"
    "<p>№ ЗП409589</p><h1>Поставка стали</h1></body>",
    # Native IDs disagree across two independently visible official fields.
    "<body><nav>Извещение о процедуре ЗП409589</nav>"
    "<p>№ ЗП409588</p><h1>Поставка стали</h1></body>",
    # Procedure ID exists only as a substring of a longer native number.
    "<body><nav>Извещение о процедуре ЗП409589</nav>"
    "<p>№ ЗП4095899</p><h1>Поставка стали</h1></body>",
    # Browser HTML heading is not actually the first-party notice title.
    "<body><nav>Извещение о процедуре ЗП409589</nav>"
    "<p>№ ЗП409589</p><h1>Товары другого заказчика</h1></body>",
])
def test_publisher_native_number_requires_two_matching_visible_fields_and_title(invalid):
    with pytest.raises(ValueError, match="title/identity mismatch"):
        validate_public_detail(invalid.encode("utf-8"), identity="20000521",
                               title="Поставка стали")


def test_native_publisher_zp_number_persists_in_actual_fetch_result(monkeypatch):
    from types import SimpleNamespace
    from contextlib import asynccontextmanager
    import asyncio
    import app.sources.tektorg_public_html as module

    actual = (
        "<body><nav>Извещение о процедуре ЗП409589</nav>"
        "<p>№ ЗП409589</p><h1>Поставка стали</h1></body>"
    ).encode()
    requests = []

    class Client:
        async def get(self, url):
            requests.append(url)
            return SimpleNamespace(
                content=listing() if url == LIST_URL else actual,
                headers={"content-type": "text/html"},
                raise_for_status=lambda: None,
            )

    @asynccontextmanager
    async def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield Client()

    monkeypatch.setattr(module, "source_client", client)
    result = asyncio.run(TekTorgPublicSource().fetch(1))
    assert result[0].external_id == "20000521"
    assert result[0].tender_number == "ЗП409589"
    assert result[0].title == "Поставка стали"
    assert requests == [LIST_URL, "https://www.tektorg.ru/223-fz/procedures/20000521"]
