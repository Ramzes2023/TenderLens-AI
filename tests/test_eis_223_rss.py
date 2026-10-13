"""Synthetic offline tests; every HTTP operation uses MockTransport."""
import asyncio
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.sources import MultiSourceFetcher, SourceRegistration, SourceRegistry
from app.sources import eis_223_rss as adapter
from app.sources.eis_rss import EisRssSource, SourceError, build_eis_rss_url, parse_eis_feed
from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch
from app.sources.models import TenderNotice


URL = adapter.build_eis_223_rss_url("кабель")
ITEM = """<item><title>Иной способ закупки №32616463738</title>
<guid>notice-1</guid><link>https://zakupki.gov.ru/notice/32616463738</link>
<pubDate>Tue, 13 Oct 2026 09:00:00 +0300</pubDate>
<description><![CDATA[<b>Поставка</b> кабеля. Размещение выполняется по: 223-ФЗ]]></description>
</item>"""


def rss(items=ITEM):
    return f'<rss version="2.0"><channel>{items}</channel></rss>'.encode()


def transport(monkeypatch, handler):
    calls, configs = [], []

    def wrapped(request):
        calls.append(request)
        return handler(request)

    def factory(**kwargs):
        configs.append(kwargs)
        # Fake CA paths need not exist; assertions inspect the real passed option.
        options = dict(kwargs, verify=True, trust_env=False,
                       transport=httpx.MockTransport(wrapped))
        return httpx.AsyncClient(**options)

    monkeypatch.setattr(adapter, "source_client", factory)
    return calls, configs


def test_url_and_existing_44_compatibility():
    term = "  алюминиевый   профиль & лист+№  "
    url = adapter.build_eis_223_rss_url(term)
    query = parse_qs(urlsplit(url).query)
    assert query == {"searchString": ["алюминиевый профиль & лист+№"],
                     "morphology": ["on"], "pageNumber": ["1"], "fz223": ["on"]}
    assert "%D0%B0" in url and "%26" in url and "%2B" in url
    assert "fz44" not in query
    assert parse_qs(urlsplit(build_eis_rss_url("кабель")).query)["fz44"] == ["on"]
    assert EisRssSource((build_eis_rss_url("кабель"),)).name == "eis"


@pytest.mark.parametrize("term", ["", " \n ", "x" * 501])
def test_invalid_terms(term):
    with pytest.raises(ValueError):
        adapter.build_eis_223_rss_url(term)


def test_bounded_terms_and_profile_clone():
    urls = adapter.build_eis_223_rss_urls(["", "Кабель", " кабель ", "лист"], max_feeds=2)
    assert len(urls) == 2
    assert len(adapter.build_eis_223_rss_urls(map(str, range(100)), max_feeds=100)) == 20
    assert len(adapter.build_eis_223_rss_urls(["а", "б"], max_feeds=0)) == 1
    assert adapter.build_eis_223_rss_urls([""] * 100 + ["лист"]) == ()
    source = adapter.Eis223RssSource((URL,), timeout=7, ca_bundle_file=Path("ca.pem"))
    clone = source.for_search_terms(["лист"])
    assert clone.urls != source.urls and clone.timeout == 7
    assert clone.ca_bundle_file == source.ca_bundle_file and clone.name == "eis_223"
    assert source.for_search_terms([]).urls == source.urls


def test_valid_rss_provenance_and_identity():
    notice = adapter.parse_eis_223_feed(rss(), feed_url=URL)[0]
    original = parse_eis_feed(rss())[0]
    assert isinstance(notice, TenderNotice)
    assert notice.identity == ("eis_223", "notice-1")
    assert notice.identity != original.identity
    assert notice.title == original.title and notice.url == original.url
    assert notice.published_at == original.published_at
    assert notice.tender_number == "32616463738"
    assert notice.requested_law == "223-FZ" and notice.observed_law == "223-FZ"
    assert notice.independently_verified_law is None
    assert notice.feed_url == URL and notice.raw_guid == "notice-1"
    assert "Поставка кабеля" in notice.raw_description


@pytest.mark.parametrize("law", ["44", "223"])
def test_observed_law_is_not_filter_or_verified_law(law):
    notice = adapter.parse_eis_223_feed(rss(ITEM.replace("223-ФЗ", law + "-ФЗ")))[0]
    assert notice.observed_law == law + "-FZ"
    assert notice.requested_law == "223-FZ"
    assert notice.independently_verified_law is None


def test_search_metadata_does_not_invent_business_fields():
    notice = adapter.parse_eis_223_feed(rss("""<item><title>Кабель</title>
    <description>Параметры поиска: 32616463738 100 руб. Закупки по: 223-ФЗ</description>
    </item>"""))[0]
    assert notice.tender_number is None and notice.observed_law is None
    assert all(getattr(notice, key) is None for key in
               ("customer", "initial_price", "currency", "deadline", "region"))


def test_guid_number_fallback_missing_values_and_duplicates():
    assert len(adapter.parse_eis_223_feed(rss(ITEM * 2))) == 1
    assert adapter.parse_eis_223_feed(rss(ITEM.replace("<guid>notice-1</guid>", "")))[0].external_id == "32616463738"
    missing = adapter.parse_eis_223_feed(rss("<item/>"))[0]
    assert missing.title and missing.url == "" and missing.published_at is None
    assert missing.tender_number is None and missing.raw_guid is None
    assert adapter.parse_eis_223_feed(rss("<item/>"))[0].identity == missing.identity
    assert len(adapter.parse_eis_223_feed(rss("<item><description>A</description></item><item><description>B</description></item>"))) == 2


def test_long_guids_do_not_collide():
    items = "".join(f"<item><guid>{'x' * 501}{suffix}</guid></item>" for suffix in "ab")
    notices = adapter.parse_eis_223_feed(rss(items))
    assert len(notices) == 2 and notices[0].identity != notices[1].identity
    assert len(notices[0].external_id) <= 500 and len(notices[0].raw_guid) == 502


def test_atom_and_empty_feeds():
    payload = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>atom-id</id><title>T</title><link href="https://zakupki.gov.ru/x"/><updated>2026-10-13</updated><summary>S</summary></entry></feed>'
    notice = adapter.parse_eis_223_feed(payload)[0]
    assert notice.external_id == "atom-id" and notice.published_at == "2026-10-13"
    assert notice.summary == "S" and notice.url.endswith("/x")
    assert adapter.parse_eis_223_feed(rss("")) == []
    assert adapter.parse_eis_223_feed(b'<feed/>') == []


@pytest.mark.parametrize("payload", [b"", b"<rss>", b"<html/>",
    b'<!DOCTYPE rss [<!ENTITY x "value">]><rss/>',
    '<!DOCTYPE rss><rss/>'.encode("utf-16")])
def test_bad_xml(payload):
    with pytest.raises(SourceError):
        adapter.parse_eis_223_feed(payload)


@pytest.mark.parametrize("url", [URL.replace("https:", "http:"),
    URL + "&fz44=on", URL.replace("fz223=on", "fz223=off"),
    URL.replace("zakupki.gov.ru", "example.test"), URL + "&fz223=on"])
def test_invalid_feed_configuration(url):
    with pytest.raises(ValueError):
        adapter.Eis223RssSource((url,))


def test_identity_cannot_be_overridden():
    with pytest.raises(TypeError):
        adapter.Eis223RssSource(name="eis")


def test_fetch_dedup_limits_tls_and_registration(monkeypatch):
    calls, configs = transport(monkeypatch, lambda request: httpx.Response(200, content=rss(ITEM * 2)))
    source = adapter.Eis223RssSource((URL, adapter.build_eis_223_rss_url("лист")), timeout=9)
    registry = SourceRegistry([SourceRegistration("eis_223", "EIS candidate", source)])
    report = asyncio.run(MultiSourceFetcher(registry).fetch())
    assert len(report.notices) == 1 and not report.failures
    assert len(calls) == 2
    assert configs[0]["verify"] is True and configs[0]["timeout"] == 9
    assert configs[0]["follow_redirects"] is False
    assert report.notices[0].feed_url == URL
    calls.clear()
    assert len(asyncio.run(source.fetch(limit=0))) == 1 and len(calls) == 1
    ca_source = adapter.Eis223RssSource((URL,), ca_bundle_file=Path("custom-ca.pem"))
    asyncio.run(ca_source.fetch())
    assert configs[-1]["verify"] == "custom-ca.pem"


def test_empty_fetch_and_page_policy(monkeypatch):
    calls, _ = transport(monkeypatch, lambda request: httpx.Response(200, content=rss("")))
    assert asyncio.run(adapter.Eis223RssSource().fetch()) == [] and not calls
    source = adapter.Eis223RssSource((URL, URL))
    with bounded_fetch(FetchPolicy(frozenset({"zakupki.gov.ru"}), max_requests=1)):
        assert asyncio.run(source.fetch()) == []
    assert len(calls) == 1


@pytest.mark.parametrize("status", [301, 403, 429, 500])
def test_http_failures(monkeypatch, status):
    transport(monkeypatch, lambda request: httpx.Response(status, content=b"", headers={"location": URL}))
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(adapter.Eis223RssSource((URL,)).fetch())


@pytest.mark.parametrize("error", [httpx.ReadTimeout("timeout"), httpx.ConnectError("TLS"), OSError("network"), ConnectorTransportError()])
def test_transport_failures(monkeypatch, error):
    def handler(request):
        raise error
    transport(monkeypatch, handler)
    with pytest.raises(type(error)):
        asyncio.run(adapter.Eis223RssSource((URL,)).fetch())


@pytest.mark.parametrize("content,headers", [(b"<rss>", {}), (b"<html/>", {}), (rss(), {"content-type": "text/html"})])
def test_fetch_bad_response(monkeypatch, content, headers):
    transport(monkeypatch, lambda request: httpx.Response(200, content=content, headers=headers))
    with pytest.raises(SourceError):
        asyncio.run(adapter.Eis223RssSource((URL,)).fetch())


def test_size_boundary_and_stream_cleanup(monkeypatch):
    # Exercise exact 5 MiB boundary without constructing millions of XML nodes.
    payload = rss("")
    exact = payload + b" " * (adapter.MAX_RESPONSE_BYTES - len(payload))
    assert adapter.parse_eis_223_feed(exact) == []
    with pytest.raises(SourceError):
        adapter.parse_eis_223_feed(exact + b" ")

    class Stream(httpx.AsyncByteStream):
        closed = False
        consumed = 0

        async def __aiter__(self):
            for _ in range(100):
                self.consumed += 1
                yield b"x" * 65536

        async def aclose(self):
            self.closed = True

    stream = Stream()
    transport(monkeypatch, lambda request: httpx.Response(200, stream=stream))
    with pytest.raises(SourceError, match="5 MiB"):
        asyncio.run(adapter.Eis223RssSource((URL,)).fetch())
    assert stream.closed and stream.consumed < 100


def test_fetch_upper_limit_and_feed_cap(monkeypatch):
    items = "".join(f"<item><guid>{index}</guid><title>T</title></item>" for index in range(110))
    calls, _ = transport(monkeypatch, lambda request: httpx.Response(200, content=rss(items)))
    assert len(asyncio.run(adapter.Eis223RssSource((URL,)).fetch(limit=500))) == 100
    calls.clear()
    calls, _ = transport(monkeypatch, lambda request: httpx.Response(200, content=rss("")))
    asyncio.run(adapter.Eis223RssSource((URL,) * 25).fetch())
    assert len(calls) == 20


def test_real_shared_client_with_mock_transport(monkeypatch):
    from app.sources.http import source_client

    monkeypatch.setattr(adapter, "source_client", lambda **kwargs: source_client(
        **dict(kwargs, trust_env=False, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=rss())
        ))
    ))
    assert asyncio.run(adapter.Eis223RssSource((URL,)).fetch())[0].identity == ("eis_223", "notice-1")
    with bounded_fetch(FetchPolicy(frozenset({"zakupki.gov.ru"}), max_requests=1)):
        assert len(asyncio.run(adapter.Eis223RssSource((URL,)).fetch())) == 1


def test_stream_timeout_closes_response(monkeypatch):
    class Stream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b"<rss>"
            raise httpx.ReadTimeout("synthetic stalled stream")

        async def aclose(self):
            self.closed = True

    stream = Stream()
    transport(monkeypatch, lambda request: httpx.Response(200, stream=stream))
    with pytest.raises(httpx.ReadTimeout):
        asyncio.run(adapter.Eis223RssSource((URL,)).fetch())
    assert stream.closed
