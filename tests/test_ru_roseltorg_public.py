"""Roseltorg public listing and independent detail verification contracts.

All HTML here is synthetic; no test below represents live source acceptance.
"""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.sources.roseltorg_public import (
    HOST, LIST_URL, RoseltorgPublicSource, parse_roseltorg_links, parse_roseltorg_detail,
)

ID = "0318300120826000550"
URL = f"https://{HOST}/procedure/{ID}/1"
TITLE = "Ремонт системы пожарной сигнализации и оповещения"


def listing(url=URL):
    return f"<html><body><a href='{url}'>Подробности</a></body></html>".encode()


def detail(number=ID, title=TITLE):
    return (f"<html><body><nav>Главная Закупки {number} Лот 1 {number} Государственные закупки</nav><h1>{title}</h1></body></html>").encode()


def test_canonical_discovery_and_verified_notice():
    assert parse_roseltorg_links(listing()) == [(ID, URL)]
    notice = parse_roseltorg_detail(detail(), identity=ID, url=URL)
    assert notice.identity == ("roseltorg_public", ID)
    assert notice.title == TITLE
    assert notice.deadline is None
    assert notice.url == URL


@pytest.mark.parametrize("bad", [
    b"", b"<html>no links</html>",
    listing(f"http://{HOST}/procedure/{ID}/1"),
    listing(f"https://{HOST}.attacker.invalid/procedure/{ID}/1"),
    listing(f"https://{HOST}/procedure/{ID}/1?key=secret"),
    listing(f"https://{HOST}/procedure/{ID}/1#part"),
    listing("https://other.example/procedure/0318300120826000550/1"),
    listing("https://www.roseltorg.ru/procedure/0318300120826000550/1%2f"),
    listing("https://www.roseltorg.ru/procedure/0318300120826000550/1\r\n"),
])
def test_unsafe_or_unavailable_listing_is_rejected(bad):
    with pytest.raises(ValueError):
        parse_roseltorg_links(bad)


@pytest.mark.parametrize("body", [
    detail(number="0318300120826000551"),
    b"<html><script>Procedure: 0318300120826000550</script><h1>Real title</h1></html>",
    b"<html><div>Number: 0318300120826000550</div><h1>Real title</h1></html>",
    detail(title=""),
    " <html><body>Процедура: 0318300120826000550</body></html>".strip().encode("utf-8"),
    b"",
])
def test_unverified_public_detail_is_rejected(body):
    with pytest.raises(ValueError):
        parse_roseltorg_detail(body, identity=ID, url=URL)


@pytest.mark.parametrize("url", [
    "http://www.roseltorg.ru/procedure/0318300120826000550/1",
    "https://other.example/procedure/0318300120826000550/1",
    "https://www.roseltorg.ru/procedure/0318300120826000550/1?x=1",
    "https://www.roseltorg.ru/procedure/0318300120826000550/2",
])
def test_mismatched_detail_url_is_rejected(url):
    with pytest.raises(ValueError):
        parse_roseltorg_detail(detail(), identity=ID, url=url)


def test_live_adapter_requests_exact_listing_and_detail(monkeypatch):
    requested = []

    class Client:
        async def get(self, url):
            requested.append(url)
            return SimpleNamespace(
                content=listing() if url == LIST_URL else detail(),
                headers={"content-type": "text/html;charset=utf-8"},
                raise_for_status=lambda: None,
            )

    @asynccontextmanager
    async def safe_client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        assert kwargs["headers"]["User-Agent"] == "Mozilla/5.0"
        yield Client()

    import app.sources.roseltorg_public as module
    monkeypatch.setattr(module, "source_client", safe_client)
    notices = asyncio.run(RoseltorgPublicSource().fetch(1))
    assert len(notices) == 1
    assert requested == [LIST_URL, URL]


def test_bounded_payload_and_conflicting_links():
    with pytest.raises(ValueError):
        parse_roseltorg_links(b"x" * 1800001)
    with pytest.raises(ValueError):
        parse_roseltorg_links(listing().replace(b"</body>",
            f"<a href='https://{HOST}/procedure/{ID}/1/'>Duplicate</a></body>".encode()), limit=3)


def test_real_job_lease_fenced_sql_roundtrip_offline(monkeypatch):
    """Synthetic Roseltorg HTML; genuine Worker and JobRepository lease/fence."""
    async def fixture_fetch(self, limit=20):
        return [parse_roseltorg_detail(detail(), identity=ID, url=URL)]

    monkeypatch.setattr(RoseltorgPublicSource, "fetch", fixture_fetch)
    from scripts.ci_ru_roseltorg_real_worker import acceptance
    evidence = acceptance()
    assert evidence["real_official_details"] == 1
    assert evidence["worker_inserted"] == 1
    assert evidence["sqlite_search_verified"] == 1
    assert evidence["idempotent"]


def test_false_visible_id_outside_official_breadcrumb_is_rejected():
    # Identity in arbitrary footer alone is not evidence of the procedure page.
    html = (f"<html><nav>Главная Закупки OTHER Лот 1 OTHER</nav>"
            f"<h1>{TITLE}</h1><footer>{ID}</footer></html>").encode()
    with pytest.raises(ValueError):
        parse_roseltorg_detail(html, identity=ID, url=URL)


def test_different_breadcrumb_lot_or_notice_id_rejected():
    wrong = (f"<html><nav>Закупки {ID} Лот 1 0318300120826000552</nav>"
             f"<h1>{TITLE}</h1></html>").encode()
    with pytest.raises(ValueError):
        parse_roseltorg_detail(wrong, identity=ID, url=URL)
