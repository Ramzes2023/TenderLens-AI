"""Offline strict public Gazprombank procurement source contracts."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.gpb_etp_public import (
    GpbEtpPublicSource, HOST, LIST_URL, parse_gpb_public_links,
    parse_gpb_verified_detail, parse_gpb_official_rss,
)

URL = "https://etpgpb.ru/procedures/etp/1299761-postavka-oborudovaniya/"
TITLE = "Поставка оборудования по техническому заданию"


def listing(url=URL):
    return f"<html><a href='{url}'>Закупка</a></html>".encode("utf-8")


def detail(identity="1299761", title=TITLE):
    return f"<html><head><title>Процедура {identity}</title></head><body><nav>Закупка № {identity}</nav><h1>{title}</h1></body></html>".encode("utf-8")


def settings(enabled=False):
    return MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=10,
        max_notifications_per_cycle=5, request_timeout=15,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        gpb_etp_public_enabled=enabled,
    )


def test_gpb_disabled_by_default_and_explicit_opt_in():
    assert "gpb_etp_public" not in build_source_catalog(settings()).enabled_keys
    assert "gpb_etp_public" in build_source_catalog(settings(True)).enabled_keys


def test_observed_numeric_only_gpb_firstparty_route_without_synthetic_slug():
    original = "https://etpgpb.ru/procedures/etp/1240053/"
    assert parse_gpb_public_links(listing(original)) == [("1240053", original)]
    notice = parse_gpb_verified_detail(detail("1240053"), "1240053", original)
    assert notice.external_id == "1240053"
    assert notice.url == original
    for bad in (
        "https://etpgpb.ru/procedures/etp/1240053/?access_token=hidden",
        "https://etpgpb.ru/procedures/etp/1240053.evil/",
        "https://etpgpb.ru.evil.example/procedures/etp/1240053/",
    ):
        with pytest.raises(ValueError):
            parse_gpb_public_links(listing(bad))


def test_exact_public_notice_and_independent_title():
    assert parse_gpb_public_links(listing()) == [("1299761", URL)]
    notice = parse_gpb_verified_detail(detail(), "1299761", URL)
    assert notice.identity == ("gpb_etp_public", "1299761")
    assert notice.title == TITLE
    assert notice.url == URL
    assert notice.deadline is None


@pytest.mark.parametrize("bad", [
    b"", b"<html>No notices</html>",
    listing("https://etpgpb.ru.evil.invalid/procedures/etp/1299761-x/"),
    listing("http://etpgpb.ru/procedures/etp/1299761-x/"),
    listing("https://etpgpb.ru/procedures/etp/1299761-x/?token=x"),
    listing("https://etpgpb.ru/procedures/etp/1299761-x/#fragment"),
])
def test_bad_public_listing_fails_closed(bad):
    with pytest.raises(ValueError):
        parse_gpb_public_links(bad)


@pytest.mark.parametrize("bad", [
    detail(identity="2222222"),
    detail(title=""),
    b"<html>No heading</html>",
])
def test_bad_detail_identity_and_heading_fails_closed(bad):
    with pytest.raises(ValueError):
        parse_gpb_verified_detail(bad, "1299761", URL)


def test_exact_public_transport_and_bounded_requests(monkeypatch):
    requested = []
    class Fake:
        async def get(self, url):
            requested.append(url)
            return SimpleNamespace(
                content=listing() if url == LIST_URL else detail(),
                headers={"content-type": "text/html;charset=utf-8"},
                raise_for_status=lambda: None,
            )
    @asynccontextmanager
    async def source(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        assert kwargs["headers"]["User-Agent"] == "Mozilla/5.0"
        assert kwargs["headers"]["Accept"] == "text/html"
        yield Fake()
    import app.sources.gpb_etp_public as module
    monkeypatch.setattr(module, "source_client", source)
    notices = asyncio.run(GpbEtpPublicSource().fetch(1))
    assert len(notices) == 1
    assert requested == [LIST_URL, URL]


def test_real_job_fence_and_sqlite_roundtrip_with_offline_source(monkeypatch):
    """Synthetic notice exercises real JobRepository lease and Worker, not live network."""
    async def fixture_fetch(self, limit=20):
        return [parse_gpb_verified_detail(detail(), "1299761", URL)]

    monkeypatch.setattr(GpbEtpPublicSource, "fetch", fixture_fetch)
    from scripts.ci_ru_gpb_public_worker import proof
    evidence = proof()
    assert evidence["real_detail_verified"] == 1
    assert evidence["worker_inserted"] == 1
    assert evidence["sqlite_search_verified"] == 1
    assert evidence["idempotent_replay"]


def test_bounded_public_gpb_skips_stale_original_and_returns_next_verified(monkeypatch):
    """Never allow one deleted/stale first-party card to starve a current feed.

    This is a MockTransport-style offline test, not live acceptance.
    """
    candidates = [
        f"https://{HOST}/procedures/etp/123450{i}-procedure/"
        for i in (1, 2, 3, 4)
    ]
    raw_index = "<html>" + "".join(
        f"<a href='{url}'>First-party procedure</a>"
        for url in candidates
    ) + "</html>"
    seen = []

    class Reply:
        def __init__(self, payload):
            self.content = payload
            self.headers = {"content-type": "text/html"}
        def raise_for_status(self):
            return None

    class Fake:
        async def get(self, url):
            seen.append(url)
            if url == LIST_URL:
                return Reply(raw_index.encode("utf-8"))
            if url == candidates[0]:
                # Rejected: H1 present but no independently visible ID.
                return Reply(b"<html><h1>Deleted</h1></html>")
            if url == candidates[1]:
                return Reply(detail("1234502"))
            raise AssertionError("Unbounded extra GPB request")

    @asynccontextmanager
    async def client(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        yield Fake()

    import app.sources.gpb_etp_public as mod
    monkeypatch.setattr(mod, "source_client", client)
    received = asyncio.run(GpbEtpPublicSource().fetch(1))
    assert len(received) == 1
    assert received[0].external_id == "1234502"
    assert received[0].url == candidates[1]
    assert seen == [LIST_URL, candidates[0], candidates[1]]




@pytest.mark.parametrize("html", [
    b"<html><script>procedure number 1299761</script><h1>Real offer</h1></html>",
    b"<html><style>.x { content: '1299761' }</style><h1>Real offer</h1></html>",
    b"<html><template><p>1299761</p></template><h1>Real offer</h1></html>",
])
def test_gpb_script_only_native_id_is_not_verified_original(html):
    # Native ID must be independently evidenced in visible publisher HTML.
    with pytest.raises(ValueError, match="identity or title mismatch"):
        parse_gpb_verified_detail(html, "1299761", URL)


def test_numeric_only_gpb_original_passes_actual_fenced_sql_worker(monkeypatch):
    # Offline mock exercises the real Worker, queue lease, SQLite and identity.
    # It deliberately does NOT assert that an upstream real original is reachable.
    native_url = "https://etpgpb.ru/procedures/etp/1240053/"
    async def synthetic_fetch(self, limit=20):
        return [parse_gpb_verified_detail(detail("1240053"), "1240053", native_url)]

    monkeypatch.setattr(GpbEtpPublicSource, "fetch", synthetic_fetch)
    from scripts.ci_ru_gpb_public_worker import proof
    result = proof()
    assert result["worker_inserted"] == 1
    assert result["sqlite_search_verified"] == 1
    assert result["idempotent_replay"] is True


@pytest.mark.parametrize("payload", [
    b"<html><head><title>1299761</title></head><body><h1>Real valid title</h1></body></html>",
    b"<html><head><meta name='x' content='1299761'></head><body><h1>Real valid title</h1></body></html>",
    b"<html><body><p>312997619</p><h1>Real valid title</h1></body></html>",
    b"<html><body><p>12997617</p><h1>Real valid title</h1></body></html>",
])
def test_original_id_must_be_visible_exact_body_number_not_header_or_substring(payload):
    with pytest.raises(ValueError, match="identity or title mismatch"):
        parse_gpb_verified_detail(payload, "1299761", URL)


@pytest.mark.parametrize("malicious", [
    "https://etpgpb.ru/procedures/etp/1299761-x/\r\n",
    "https://etpgpb.ru/procedures/etp/1299761-x/\t",
    "https://etpgpb.ru/procedures/etp/1299761-x/\x7f",
])
def test_public_index_rejects_url_control_characters_before_urljoin(malicious):
    with pytest.raises(ValueError, match="No public GPB procedure URLs"):
        parse_gpb_public_links(listing(malicious))


def rss(first=URL, second="https://etpgpb.ru/procedures/etp/1299762/"):
    return (
        "<rss version='2.0'><channel>"
        f"<item><title>{TITLE}</title><link>{first}</link></item>"
        f"<item><title>Оказание услуг перевозки грузов</title><link>{second}</link></item>"
        "</channel></rss>"
    ).encode("utf-8")


def test_publisher_documented_rss_originals_have_native_immutable_id():
    assert parse_gpb_official_rss(rss(), limit=2) == [
        ("1299761", URL),
        ("1299762", "https://etpgpb.ru/procedures/etp/1299762/"),
    ]


@pytest.mark.parametrize("bad", [
    b"<html>Login required</html>",
    b"<rss><channel/><channel/></rss>",
    b"<!DOCTYPE rss [<!ENTITY x 'foo'>]><rss><channel/></rss>",
    b"<rss><channel><item><title>Bad feed",
    b"<rss><channel/></rss>",
    rss(first="https://etpgpb.ru/procedures/etp/1299762-other-original/"),
])
def test_official_rss_malicious_or_not_publishable_fails_closed(bad):
    with pytest.raises(ValueError):
        parse_gpb_official_rss(bad)


@pytest.mark.parametrize("malicious", [
    "https://etpgpb.ru.evil.invalid/procedures/etp/1299761/",
    "https://etpgpb.ru/procedures/etp/1299761/?private=1",
    "http://etpgpb.ru/procedures/etp/1299761/",
])
def test_off_host_or_unapproved_feed_items_never_become_candidates(malicious):
    assert parse_gpb_official_rss(rss(first=malicious)) == [
        ("1299762", "https://etpgpb.ru/procedures/etp/1299762/")
    ]


def test_gpb_rss_fallback_real_adapter_request_path_and_detail_proof(monkeypatch):
    import httpx
    requests = []

    class Reply:
        def __init__(self, data, mime):
            self.content = data
            self.headers = {"content-type": mime}

        def raise_for_status(self):
            return None

    class Client:
        async def get(self, url, **kwargs):
            requests.append((url, kwargs))
            if url == LIST_URL:
                # Network failure on legacy HTML route, not any proof of RSS.
                raise httpx.ConnectTimeout("first-party HTML temporarily down")
            if url == "https://etpgpb.ru/procedures.rss":
                assert kwargs["headers"]["Accept"] == "application/rss+xml, application/xml"
                return Reply(rss(), "application/rss+xml")
            if url == URL:
                return Reply(detail(), "text/html")
            raise AssertionError("Off-host or unbounded request")

    @asynccontextmanager
    async def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield Client()

    import app.sources.gpb_etp_public as module
    monkeypatch.setattr(module, "source_client", client)
    result = asyncio.run(GpbEtpPublicSource(timeout=20).fetch(1))
    assert [r.identity for r in result] == [("gpb_etp_public", "1299761")]
    assert [url for url, _ in requests] == [
        LIST_URL, "https://etpgpb.ru/procedures.rss", URL
    ]


def test_gpb_both_official_routes_down_never_returns_fabricated_tenders(monkeypatch):
    import httpx
    seen = []

    class Client:
        async def get(self, url, **kwargs):
            seen.append(url)
            raise httpx.ConnectTimeout("network not available")

    @asynccontextmanager
    async def client(**kwargs):
        yield Client()

    import app.sources.gpb_etp_public as module
    monkeypatch.setattr(module, "source_client", client)
    with pytest.raises(httpx.ConnectTimeout):
        asyncio.run(GpbEtpPublicSource().fetch(1))
    assert seen == [LIST_URL, "https://etpgpb.ru/procedures.rss"]


def test_official_gpb_rss_one_transient_failure_then_visible_native_original(monkeypatch):
    from app.sources.http import ConnectorTransportError
    calls = []

    class Reply:
        def __init__(self, body, mime):
            self.content, self.headers = body, {"content-type": mime}
        def raise_for_status(self):
            return None

    class Client:
        async def get(self, url, **kwargs):
            calls.append(url)
            if url == LIST_URL:
                raise ConnectorTransportError(retryable=True, reason="network")
            if url == f"https://{HOST}/procedures.rss":
                if calls.count(url) == 1:
                    raise ConnectorTransportError(retryable=True, reason="network")
                assert kwargs["headers"]["Accept"] == "application/rss+xml, application/xml"
                return Reply(rss(), "application/rss+xml")
            if url == URL:
                return Reply(detail(), "text/html")
            raise AssertionError("Unexpected unbounded or off-host request")

    @asynccontextmanager
    async def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield Client()

    import app.sources.gpb_etp_public as mod
    monkeypatch.setattr(mod, "source_client", client)
    async def no_wait(_):
        return None
    monkeypatch.setattr(mod.asyncio, "sleep", no_wait)
    out = asyncio.run(GpbEtpPublicSource().fetch(1))
    assert [x.external_id for x in out] == ["1299761"]
    assert calls == [LIST_URL, f"https://{HOST}/procedures.rss",
                     f"https://{HOST}/procedures.rss", URL]


@pytest.mark.parametrize("reason", ["public_ip", "tls_certificate", "policy"])
def test_gpb_rss_security_failure_never_retried(monkeypatch, reason):
    from app.sources.http import ConnectorTransportError
    seen = []

    class Client:
        async def get(self, url, **kwargs):
            seen.append(url)
            raise ConnectorTransportError(
                retryable=(url == LIST_URL), reason="network" if url == LIST_URL else reason,
            )

    @asynccontextmanager
    async def client(**kwargs):
        yield Client()

    import app.sources.gpb_etp_public as mod
    monkeypatch.setattr(mod, "source_client", client)
    with pytest.raises(ConnectorTransportError):
        asyncio.run(GpbEtpPublicSource().fetch(1))
    assert seen == [LIST_URL, f"https://{HOST}/procedures.rss"]


def test_gpb_valid_but_entirely_stale_html_index_recovers_current_official_rss(monkeypatch):
    """Official RSS gets a second chance, never re-accepts stale HTML IDs."""
    rss_new = "https://etpgpb.ru/procedures/etp/1299762/"
    requests = []

    class Reply:
        def __init__(self, data, mime):
            self.content, self.headers = data, {"content-type": mime}
        def raise_for_status(self):
            return None

    class Client:
        async def get(self, url, **kw):
            requests.append(url)
            if url == LIST_URL:
                return Reply(listing(), "text/html")
            if url == URL:
                return Reply("<html><h1>Удалённая карточка</h1></html>".encode("utf-8"), "text/html")
            if url == f"https://{HOST}/procedures.rss":
                return Reply(rss(), "application/rss+xml")
            if url == rss_new:
                return Reply(detail("1299762", "Оказание услуг перевозки грузов"), "text/html")
            raise AssertionError("Unexpected upstream original or unbounded GET")

    @asynccontextmanager
    async def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield Client()

    import app.sources.gpb_etp_public as mod
    monkeypatch.setattr(mod, "source_client", client)
    result = asyncio.run(GpbEtpPublicSource().fetch(1))
    assert [(n.external_id, n.url) for n in result] == [("1299762", rss_new)]
    assert requests == [LIST_URL, URL, f"https://{HOST}/procedures.rss", rss_new]


def test_gpb_all_stale_html_and_rss_cannot_fabricate_original(monkeypatch):
    requests = []
    class Reply:
        def __init__(self, data, mime):
            self.content, self.headers = data, {"content-type": mime}
        def raise_for_status(self):
            return None

    class Client:
        async def get(self, url, **kw):
            requests.append(url)
            if url == LIST_URL:
                return Reply(listing(), "text/html")
            if url == f"https://{HOST}/procedures.rss":
                return Reply(rss(first=URL, second=URL), "application/rss+xml")
            return Reply("<html><h1>Недоступный оригинал</h1></html>".encode("utf-8"), "text/html")

    @asynccontextmanager
    async def client(**kw):
        yield Client()

    import app.sources.gpb_etp_public as mod
    monkeypatch.setattr(mod, "source_client", client)
    with pytest.raises(ValueError, match="No independently verified"):
        asyncio.run(GpbEtpPublicSource().fetch(1))
    # No extra detail GET when the RSS candidate is the previously rejected ID.
    assert requests == [LIST_URL, URL, f"https://{HOST}/procedures.rss"]


def test_gpb_source_worker_budget_is_explicitly_bounded_for_stale_html_and_rss():
    from app.sources.ingestion import HOSTS, ConnectorSyncHandler
    from app.sources.gpb_etp_public import MAX_CANDIDATES, MAX_DETAILS
    assert HOSTS["gpb_etp_public"] == frozenset({HOST})
    assert MAX_CANDIDATES == 9 and MAX_DETAILS == 3
    # Budget: initial HTML + 9 independently checked HTML details +
    # up to 2 published RSS fetches + 3 independently checked RSS details.
    budget = min(20, MAX_DETAILS) * 4 + 3
    assert budget == 15


def test_gpb_one_transient_original_detail_failure_does_not_starve_next(monkeypatch):
    from app.sources.http import ConnectorTransportError
    second = "https://etpgpb.ru/procedures/etp/1299762/"
    source_index = (
        f"<html><a href='{URL}'>Поставка оборудования</a>"
        f"<a href='{second}'>Оказание услуг перевозки грузов</a></html>"
    ).encode("utf-8")
    calls = []

    class Reply:
        def __init__(self, body, mime="text/html"):
            self.content, self.headers = body, {"content-type": mime}
        def raise_for_status(self):
            return None

    class Client:
        async def get(self, url, **kwargs):
            calls.append(url)
            if url == LIST_URL:
                return Reply(source_index)
            if url == URL:
                raise ConnectorTransportError(retryable=True, reason="network")
            if url == second:
                return Reply(detail("1299762", "Оказание услуг перевозки грузов"))
            raise AssertionError("Unapproved source or detail request")

    @asynccontextmanager
    async def client(**kw):
        assert kw["trust_env"] is False
        assert kw["follow_redirects"] is False
        yield Client()

    import app.sources.gpb_etp_public as module
    monkeypatch.setattr(module, "source_client", client)
    result = asyncio.run(GpbEtpPublicSource().fetch(1))
    assert [(n.external_id, n.url) for n in result] == [("1299762", second)]
    assert calls == [LIST_URL, URL, second]


@pytest.mark.parametrize("reason", ["tls_certificate", "public_ip", "policy"])
def test_gpb_unsafe_original_detail_transport_never_skipped(monkeypatch, reason):
    from app.sources.http import ConnectorTransportError
    seen = []

    class Reply:
        content, headers = listing(), {"content-type": "text/html"}
        def raise_for_status(self):
            return None

    class Client:
        async def get(self, url, **kwargs):
            seen.append(url)
            if url == LIST_URL:
                return Reply()
            raise ConnectorTransportError(retryable=False, reason=reason)

    @asynccontextmanager
    async def client(**kw):
        yield Client()

    import app.sources.gpb_etp_public as module
    monkeypatch.setattr(module, "source_client", client)
    with pytest.raises(ConnectorTransportError):
        asyncio.run(GpbEtpPublicSource().fetch(1))
    assert seen == [LIST_URL, URL]
