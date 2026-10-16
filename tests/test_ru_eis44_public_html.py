"""Offline legal/identity contracts for official EIS 44-FZ HTML results."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.eis_44_public_html import (
    Eis44PublicHtmlSource,
    HOST,
    LIST_URL,
    SOURCE_ID,
    parse_official_44_listing,
)
from app.scoring.runs import validate_configuration

NUMBER = "0316300145126000012"
URL = f"https://{HOST}/epz/order/notice/ezt20/view/common-info.html?regNumber={NUMBER}"
TITLE = "Закупка, осуществляемая в соответствии с частью 12 статьи 93 Закона № 44-ФЗ"


def fixture(number=NUMBER, title=TITLE, law="44-ФЗ", link=URL):
    return (f"<html><div class='search-registry-entry-block'><div>"
            f"{law} {title}</div><div><a href='{link}'>№ {number}</a></div>"
            f"<div>Начальная цена 56 000,00 ₽</div></div></html>").encode()


def settings(ca=None, enabled=False):
    return MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=10,
        max_notifications_per_cycle=5, request_timeout=15,
        eis_rss_urls=(), ca_bundle_file=ca,
        profile_feeds_enabled=False, eis_44_html_enabled=enabled,
    )


def test_rejects_untrusted_or_missing_operator_ca(tmp_path):
    assert SOURCE_ID not in build_source_catalog(settings()).enabled_keys
    with pytest.raises(ValueError, match="CA"):
        build_source_catalog(settings(enabled=True))
    ca = tmp_path / "reviewed.pem"
    ca.write_text("placeholder used only by offline mocked HTTP")
    assert SOURCE_ID in build_source_catalog(settings(ca, True)).enabled_keys
    assert validate_configuration([SOURCE_ID], 10)["sources"] == [SOURCE_ID]


def test_official_result_has_stable_identity_and_law():
    notices = parse_official_44_listing(fixture())
    assert len(notices) == 1
    row = notices[0]
    assert row.identity == (SOURCE_ID, NUMBER)
    assert row.title == TITLE
    assert row.url == URL
    assert row.tender_number == NUMBER
    assert row.initial_price == 56000.0
    assert row.currency == "RUB"
    assert row.customer is None  # Only extract customer from a labelled field


@pytest.mark.parametrize("body", [
    fixture(law="223-ФЗ"),
    fixture(law="44-ФЗ", link=f"https://evil.invalid/view/common-info.html?regNumber={NUMBER}"),
    fixture(law="44-ФЗ", link=f"http://{HOST}/epz/order/notice/ezt20/view/common-info.html?regNumber={NUMBER}"),
    fixture(law="44-ФЗ", link=f"https://{HOST}/epz/order/notice/ezt20/view/common-info.html?regNumber={NUMBER}&token=secret"),
    fixture(law="44-ФЗ", link=f"https://{HOST}/epz/order/notice/ezt20/view/common-info.html?regNumber=123"),
    fixture(law="44-ФЗ", number="9000000000000000000"),
    fixture(law="44-ФЗ", title="X"),
    b"<html></html>",
    b"",
])
def test_incomplete_result_cannot_be_ingested(body):
    with pytest.raises(ValueError):
        parse_official_44_listing(body)


def test_conflicting_duplicate_number_fails_closed():
    data = fixture().replace(b"</html>", b"")
    second = fixture(title="Different procurement").replace(b"<html>", b"")
    with pytest.raises(ValueError):
        parse_official_44_listing(data + second, limit=3)


def test_fetch_is_bounded_tls_and_source_scoped_offline(tmp_path, monkeypatch):
    ca = tmp_path / "reviewed.pem"
    ca.write_text("mock-CA")
    called = []

    class Response:
        content = fixture()
        headers = {"content-type": "text/html;charset=UTF-8"}
        def raise_for_status(self):
            return None

    class FakeClient:
        async def get(self, url):
            called.append(url)
            return Response()

    @asynccontextmanager
    async def fake_client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        assert kwargs["verify"] == str(ca)
        yield FakeClient()

    import app.sources.eis_44_public_html as module
    monkeypatch.setattr(module, "source_client", fake_client)
    notices = asyncio.run(Eis44PublicHtmlSource(ca_bundle_file=ca).fetch(10))
    assert called == [LIST_URL]
    assert len(notices) == 1
    assert notices[0].source == SOURCE_ID

def test_extracts_only_labelled_customer_and_publication_date():
    body = fixture().replace(
        "Начальная цена 56 000,00 ₽".encode(),
        "Заказчик МБУ «УМКА» Начальная цена 56 000,00 ₽ Размещено 16.10.2026".encode(),
    )
    notice = parse_official_44_listing(body)[0]
    assert notice.customer == "МБУ «УМКА»"
    assert notice.initial_price == 56000.0
    assert notice.published_at == "16.10.2026"
    assert notice.deadline is None

def test_invalid_optional_date_does_not_discard_verified_official_identity():
    body = fixture().replace(
        "Начальная цена 56 000,00 ₽".encode(),
        "Начальная цена 56 000,00 ₽ Размещено 99.99.2026".encode(),
    )
    notice = parse_official_44_listing(body)[0]
    assert notice.identity == (SOURCE_ID, NUMBER)
    assert notice.url == URL
    assert notice.published_at is None
    assert notice.initial_price is None  # all untrusted optional fields discarded
