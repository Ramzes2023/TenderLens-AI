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


@pytest.mark.parametrize("hidden", ["head", "template", "noscript", "svg", "script"])
def test_hidden_roseltorg_original_link_is_not_public_discovery(hidden):
    body = (f"<html><{hidden}><a href='{URL}'>Invisible prototype</a>"
            f"</{hidden}><body>No public procedures here</body></html>").encode()
    with pytest.raises(ValueError, match="No independently discoverable"):
        parse_roseltorg_links(body)


def test_hidden_prototype_does_not_override_visible_roseltorg_original():
    mock = (f"<template><a href='{URL}'>Invisible ID</a></template>").encode()
    assert parse_roseltorg_links(mock + listing()) == [(ID, URL)]


def test_exact_roseltorg_procedure_breadcrumb_only_in_html_title_is_not_proof():
    body = (
        f"<html><head><title>Закупки {ID} Лот 1 {ID}</title></head>"
        f"<body><h1>{TITLE}</h1></body></html>"
    ).encode()
    with pytest.raises(ValueError, match="breadcrumb identity mismatch"):
        parse_roseltorg_detail(body, identity=ID, url=URL)


def test_stale_first_official_cards_do_not_starve_later_verified_original(monkeypatch):
    """Offline transport simulation only, NOT evidence of a reachable source."""
    ids = [f"03183001208260005{x:02d}" for x in (50, 51, 52, 53)]
    links = [f"https://{HOST}/procedure/{n}/1" for n in ids]
    index = ("<html>" + "".join(
        f"<a href='{url}'>Официальная закупка</a>" for url in links
    ) + "</html>").encode("utf-8")
    seen = []

    class Reply:
        def __init__(self, body):
            self.content = body
            self.headers = {"content-type": "text/html"}
        def raise_for_status(self):
            return None

    class Client:
        async def get(self, url):
            seen.append(url)
            if url == LIST_URL:
                return Reply(index)
            if url in links[:2]:
                # Removed entries are not independent real procurement details.
                return Reply(b"<html><h1>Извещение удалено</h1></html>")
            if url == links[2]:
                return Reply(detail(number=ids[2]))
            raise AssertionError("Exceeded bounded one-original verification")

    @asynccontextmanager
    async def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield Client()

    import app.sources.roseltorg_public as module
    monkeypatch.setattr(module, "source_client", client)
    actual = asyncio.run(RoseltorgPublicSource().fetch(1))
    assert [v.external_id for v in actual] == ids[2:3]
    assert [v.url for v in actual] == links[2:3]
    assert seen == [LIST_URL, links[0], links[1], links[2]]


def test_roseltorg_stale_candidates_have_strict_maximum():
    from app.sources.roseltorg_public import MAX_CANDIDATES, MAX_DETAILS
    assert MAX_CANDIDATES == 9 and MAX_DETAILS == 3
    with pytest.raises(ValueError, match="bound"):
        parse_roseltorg_links(listing(), limit=10)
    with pytest.raises(ValueError, match="bound"):
        parse_roseltorg_links(listing(), limit=True)


def test_all_unverified_stale_cards_never_claim_success(monkeypatch):
    entries = [f"https://{HOST}/procedure/03183001208260005{x:02d}/1"
               for x in range(9)]
    index = ("<html>" + "".join(
        f"<a href='{u}'>Опубликованная процедура</a>" for u in entries
    ) + "</html>").encode()
    requests = []

    class Reply:
        def __init__(self, body):
            self.content = body
            self.headers = {"content-type": "text/html"}
        def raise_for_status(self):
            return None

    class Client:
        async def get(self, url):
            requests.append(url)
            return Reply(index if url == LIST_URL else b"<h1>Removed</h1>")

    @asynccontextmanager
    async def client(**kwargs):
        yield Client()

    import app.sources.roseltorg_public as module
    monkeypatch.setattr(module, "source_client", client)
    with pytest.raises(ValueError, match="No independently verified"):
        asyncio.run(RoseltorgPublicSource().fetch(3))
    assert requests == [LIST_URL] + entries


def test_transient_official_detail_transport_does_not_starve_next_valid_original(monkeypatch):
    from app.sources.http import ConnectorTransportError
    second = "0318300120826000551"
    second_url = f"https://{HOST}/procedure/{second}/1"
    pairs = (listing().replace(b"</body>", b"") +
             f"<a href='{second_url}'>Вторая реальная закупка</a></body></html>".encode())
    requested = []

    class Reply:
        def __init__(self, body):
            self.content, self.headers = body, {"content-type": "text/html"}
        def raise_for_status(self):
            return None

    class Client:
        async def get(self, url):
            requested.append(url)
            if url == LIST_URL:
                return Reply(pairs)
            if url == URL:
                raise ConnectorTransportError(retryable=True, reason="network")
            if url == second_url:
                return Reply(detail(number=second, title="Ремонт офисных помещений"))
            raise AssertionError("Unexpected publisher request")

    @asynccontextmanager
    async def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield Client()

    import app.sources.roseltorg_public as mod
    monkeypatch.setattr(mod, "source_client", client)
    actual = asyncio.run(RoseltorgPublicSource().fetch(1))
    assert [(n.external_id, n.url) for n in actual] == [(second, second_url)]
    assert requested == [LIST_URL, URL, second_url]


@pytest.mark.parametrize("reason", ["tls_certificate", "public_ip", "policy"])
def test_nonretryable_detail_transport_failure_is_never_skipped(monkeypatch, reason):
    from app.sources.http import ConnectorTransportError
    requested = []

    class Reply:
        content, headers = listing(), {"content-type": "text/html"}
        def raise_for_status(self):
            return None

    class Client:
        async def get(self, url):
            requested.append(url)
            if url == LIST_URL:
                return Reply()
            raise ConnectorTransportError(retryable=False, reason=reason)

    @asynccontextmanager
    async def client(**kwargs):
        yield Client()

    import app.sources.roseltorg_public as mod
    monkeypatch.setattr(mod, "source_client", client)
    with pytest.raises(ConnectorTransportError):
        asyncio.run(RoseltorgPublicSource().fetch(1))
    assert requested == [LIST_URL, URL]
