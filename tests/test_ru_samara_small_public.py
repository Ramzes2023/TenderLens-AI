"""Offline hostile HTML fixtures never count as live procurement evidence."""
import asyncio
import httpx
import pytest
from app.sources.http import ConnectorTransportError
from scripts.research_ru_samara_small_public import (
    HOST, INDEX, GRID_URL, listing, strict_original_link, original_detail,
    disclosed_grid_paths, describe_public_json_shape, disclosed_json_grid_method,
    probe_disclosed_public_json,
)

A = "ИМЗ-2026-0-223-000399"
B = "ИМЗ-2026-0-223-000480"
X = "Поставка рулонных штор для школы"
Y = "Приобретение запасных частей для автотранспорта"
FIRST = "/public/notice/detail?id=399"
SECOND = "/public/notice/detail?id=480"


def synthetic_index():
    return (f"""<html><table>
        <tr><td>{A}</td><td><a href="{FIRST}">{X}</a></td></tr>
        <tr><td>{B}</td><td><a href="{SECOND}">{Y}</a></td></tr>
        </table></html>""").encode("utf-8")


def synthetic_detail(number, title):
    return (f"<html><h1>{title}</h1><table><tr><th>Номер</th><td>{number}</td></tr>"
            "<tr><th>Заказчик</th><td>Самарская организация</td></tr>"
            "<tr><th>Цена</th><td>135000 RUB</td></tr></table></html>").encode("utf-8")


def test_two_distinct_firstparty_original_details():
    verified = listing(synthetic_index())
    assert len(verified) == 2
    for number, title, url in verified:
        assert original_detail(synthetic_detail(number, title), number, title, url) == (number, title, url)


@pytest.mark.parametrize("href", [
    "http://webtorgi.samregion.ru/public/notice/detail?id=399",
    "https://webtorgi.samregion.ru.evil.example/public/notice/detail?id=399",
    "https://evil.example/public/notice/detail?id=399",
    "//evil.example/public/notice/detail?id=399",
    "https://user:password@webtorgi.samregion.ru/public/notice/detail?id=399",
    "/public/notice/detail?id=399&redirect=https://evil.example",
    "/public/notice/detail?id=399#fragment",
    "/login", "/",
    "/public/notice/detail?id=399%0d%0aLocation:",
])
def test_reject_untrusted_url(href):
    assert strict_original_link(href) is None


def test_login_scripts_and_single_offer_never_green():
    for raw in (
        b"<html>Login</html>",
        synthetic_index().replace(B.encode(), A.encode()),
        f'<script><tr><td>{A}</td><a href="{FIRST}">{X}</a></tr></script>'.encode(),
        f'<table><tr><td>{A}</td><a href="{FIRST}">{X}</a></tr></table>'.encode(),
    ):
        with pytest.raises(ValueError):
            listing(raw)


def test_independent_details_must_match_buyer_and_price():
    indexed = listing(synthetic_index())
    n, title, url = indexed[0]
    for html in (
        synthetic_detail("ИМЗ-2026-0-223-000111", title),
        synthetic_detail(n, "Другой предмет закупки"),
        synthetic_detail(n, title).replace("Заказчик".encode(), "Продавец".encode()),
        synthetic_detail(n, title).replace("Цена".encode(), "Статус".encode()),
        f"<script>{n} {title} Заказчик: ООО Цена: 1</script>".encode("utf-8"),
    ):
        with pytest.raises(ValueError):
            original_detail(html, n, title, url)


def test_exact_origin():
    assert HOST == "webtorgi.samregion.ru"
    assert INDEX == "https://webtorgi.samregion.ru/smallpurchases/Menu/Page/1"
    assert GRID_URL == "https://webtorgi.samregion.ru/smallpurchases/GzwSP/NoticesGrid"

def test_disclosed_native_grid_paths_are_diagnostic_only():
    script = (b'<script>var grid={url:"/smallpurchases/GzwSP/NoticesJson"};'
              b'var next="/smallpurchases/GzwSP/NoticesExport?page=1";</script>')
    assert disclosed_grid_paths(script) == (
        "/smallpurchases/GzwSP/NoticesExport",
        "/smallpurchases/GzwSP/NoticesJson",
    )
    with pytest.raises(ValueError):
        listing(script)  # Inline JavaScript does not prove actual native notices.
    with pytest.raises(ValueError):
        disclosed_grid_paths(b"")
    with pytest.raises(ValueError):
        disclosed_grid_paths(b"test\x00more")

def test_public_json_is_diagnostic_and_never_fake_original_notice_proof():
    payload = b'{"total":17,"page":1,"rows":[{"id":1},{"id":2}]}'
    detail = describe_public_json_shape(payload)
    assert detail["root"] == "object"
    assert detail["rows"] == 2
    assert detail["native_ids_visible"] == 0
    assert detail["keys"] == ("page", "rows", "total")
    assert describe_public_json_shape(b'[]')["root"] == "array"
    for bad in (b"", b"null", b"{", b"123", b"hello", b'{"a":1}\x00'):
        with pytest.raises((ValueError, UnicodeError)):
            describe_public_json_shape(bad)

def test_samara_disclosed_public_grid_method_is_not_live_proof():
    assert disclosed_json_grid_method(b"<html></html>") == "NOT_DISCLOSED"
    url = b'/smallpurchases/GzwSP/NoticesJson'
    assert disclosed_json_grid_method(
        b'<script>var list={url:"' + url + b'",mtype:"POST"};</script>'
    ) == "POST"
    assert disclosed_json_grid_method(
        b'<script>var list={url:"' + url + b'",mtype:"GET"};</script>'
    ) == "GET"
    assert disclosed_json_grid_method(
        b'<script>var list={url:"' + url + b'"};</script>'
    ) == "UNKNOWN"

class _CookieJar:
    def __init__(self): self.clear_count = 0
    def clear(self): self.clear_count += 1


class _ReadOnlyFake:
    def __init__(self, *, retryable=False):
        self.cookies = _CookieJar()
        self.methods = []
        self.retryable = retryable

    async def request(self, method, url, **kwargs):
        self.methods.append((method, url, kwargs))
        if method == "GET":
            raise ConnectorTransportError(retryable=self.retryable)
        return httpx.Response(
            200, headers={"content-type": "application/json"},
            content=b'{"page":1,"rows":[{"id":"example"}],"total":1}',
        )


def test_public_notices_json_may_probe_empty_anonymous_post_but_never_claim_live(capsys):
    html = b'<script>var grid={url:"/smallpurchases/GzwSP/NoticesJson"};</script>'
    client = _ReadOnlyFake()
    assert asyncio.run(probe_disclosed_public_json(client, html)) is None
    assert [x[0] for x in client.methods] == ["GET", "POST"]
    assert {x[1] for x in client.methods} == {
        "https://webtorgi.samregion.ru/smallpurchases/GzwSP/NoticesJson"
    }
    assert client.methods[1][2]["content"] == b""
    assert "Cookie" not in client.methods[1][2]["headers"]
    assert client.cookies.clear_count >= 4
    output = capsys.readouterr().out
    assert "STRUCTURE_ONLY_NOT_ORIGINALS" in output
    assert "PASS" not in output
    assert "NATIVE_IDS=0" in output


def test_json_probe_does_not_retry_outage_or_override_get_only(capsys):
    url = b'/smallpurchases/GzwSP/NoticesJson'
    for html, retryable in (
        (b'<script>var grid={url:"' + url + b'"};</script>', True),
        (b'<script>var grid={url:"' + url + b'",mtype:"GET"};</script>', False),
    ):
        client = _ReadOnlyFake(retryable=retryable)
        asyncio.run(probe_disclosed_public_json(client, html))
        assert [method for method, _, _ in client.methods] == ["GET"]
    not_listed = _ReadOnlyFake()
    asyncio.run(probe_disclosed_public_json(not_listed, b'<html/>'))
    assert not not_listed.methods
