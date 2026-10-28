"""Synthetic GPB Gos44 contracts: never live tender proof."""
import asyncio
from contextlib import asynccontextmanager
from urllib.parse import quote

import pytest

from scripts import research_ru_gpb_gos44_published_current as m

A = "0832200006626000852"
B = "0142200001326020312"
URL_A = (
    "https://gos.etpgpb.ru/front/procedure/view/"
    "c0b23def-d821-490b-b4e3-7142596163da?backurl=" + quote(m.BACKURL, safe="")
)
URL_B = (
    "https://gos.etpgpb.ru/front/procedure/view/"
    "dbd038e7-9c2e-41d5-a8a4-5c821a43c07c?backurl=" + quote(m.BACKURL, safe="")
)
TITLE_A = "Капитальный ремонт автомобильных дорог регионального значения"
TITLE_B = "Поставка нефтепродуктов для нужд больницы Самарской области"


def listing():
    return (
        "<html><body><table><tbody>"
        f"<tr><td>ЭК</td><td><a href='{URL_A}'>{TITLE_A}</a>"
        f" ({A})</td><td>Нижегородская область</td></tr>"
        f"<tr><td>ЭА</td><td><a href='{URL_B}'>{TITLE_B}</a>"
        f" ({B})</td><td>Самарская область</td></tr>"
        "</tbody></table></body></html>"
    ).encode("utf-8")


def detail(number=A, title=TITLE_A):
    return (
        f"<html><head><title>Страница процедуры</title></head><body>"
        f"<h1>Сведения о процедуре ЭК {number}</h1>"
        f"<section>Номер извещения <a href='https://zakupki.gov.ru'>{number}</a></section>"
        f"<p>Наименование объекта закупки {title} "
        f"Идентификационный код закупки 262525705616352570100103170014211243</p>"
        "</body></html>"
    ).encode("utf-8")


def test_exact_original_firstparty_published_urls_and_live_shape():
    assert m.LIST_URL == "https://gos.etpgpb.ru/44/catalog/procedure/published"
    assert m.canonical(URL_A) == URL_A
    assert m.canonical(URL_B) == URL_B
    assert m.published_candidates(listing()) == [
        (A, TITLE_A, URL_A), (B, TITLE_B, URL_B),
    ]
    assert m.independently_verify_detail(detail(), A, TITLE_A, URL_A)[0] == A


@pytest.mark.parametrize("hostile", [
    URL_A.replace("https://", "http://"),
    URL_A.replace("gos.etpgpb.ru", "evil.invalid"),
    URL_A.replace("gos.etpgpb.ru", "gos.etpgpb.ru.evil.invalid"),
    URL_A.replace("?backurl=", "?auth=ok&backurl="),
    URL_A.replace("?backurl=", "?backurl=other&backurl="),
    URL_A.replace("/front/", "/encoded%2ffront/"),
    URL_A + "#fragment",
    URL_A + "\r\n",
    URL_A.replace("c0b23def-d821-490b-b4e3-7142596163da", "../"),
])
def test_only_publisher_original_exact_host_and_fixed_backlink(hostile):
    assert m.canonical(hostile) is None


@pytest.mark.parametrize("hidden", ["template", "script", "head", "noscript", "svg"])
def test_hidden_publisher_prototype_links_are_not_current_publications(hidden):
    payload = (f"<html><{hidden}><table><tr><td>{A}</td>"
               f"<td><a href='{URL_A}'>{TITLE_A}</a></td></tr></table>"
               f"</{hidden}><p>No real publications</p></html>").encode()
    with pytest.raises(ValueError, match="fewer than two"):
        m.published_candidates(payload)


def test_duplicate_cross_eis_numbers_are_not_invented_new_procurements():
    row = (f"<tr><td><a href='{URL_A}'>{TITLE_A}</a> ({A})</td></tr>")
    bad = ("<table>" + row + row + "</table>").encode()
    with pytest.raises(ValueError, match="fewer than two"):
        m.published_candidates(bad)


@pytest.mark.parametrize("bad", [
    detail(number="0832200006626000853"),
    detail().replace(b"0832200006626000852", b"10832200006626000852"),
    f"<html><head><title>Сведения о процедуре ЭК {A}</title></head>"
    f"<body><p>Номер извещения {A}</p>"
    f"<p>Наименование объекта закупки {TITLE_A} Идентификационный код закупки</p></body></html>",
    f"<html><script>Номер извещения {A}</script>"
    f"<p>Наименование объекта закупки {TITLE_A} Идентификационный код закупки</p></html>",
    detail(title="Совершенно другой предмет закупки"),
])
def test_invalid_or_hidden_official_detail_rejected(bad):
    if type(bad) is str:
        bad = bad.encode()
    with pytest.raises(ValueError):
        m.independently_verify_detail(bad, A, TITLE_A, URL_A)


def test_two_distinct_real_pipeline_stages_offline_only(monkeypatch):
    calls = []
    class Reply:
        def __init__(self, body):
            self.content = body
            self.headers = {"content-type": "text/html"}
        def raise_for_status(self):
            return None

    class Client:
        async def get(self, url):
            calls.append(url)
            if url == m.LIST_URL:
                return Reply(listing())
            if url == URL_A:
                return Reply(detail())
            if url == URL_B:
                return Reply(detail(number=B, title=TITLE_B))
            raise AssertionError("Undocumented outbound URL")

    @asynccontextmanager
    async def client(**kw):
        assert kw["trust_env"] is False
        assert kw["follow_redirects"] is False
        yield Client()

    monkeypatch.setattr(m, "source_client", client)
    result = asyncio.run(m.current_publisher_proof())
    assert len(result) == 2
    assert [x[0] for x in result] == [A, B]
    assert calls == [m.LIST_URL, URL_A, URL_B]
