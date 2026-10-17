"""Strict contracts for NMCK official first-party discovery; fixtures NOT live."""
import pytest
from app.sources.nmck_native_public import parse_list, safe_slug, verify_detail, NmckNativePublicSource, LIST_URL

HOST = "xn--j1adc1b.xn--p1ai"
SLUG1 = "postavka-moyushchih-sredst-20261000009m"
SLUG2 = "postavka-bumagi-dlya-ofisnoy-tehniki-20261000008m"
TITLE1 = "Поставка моющих средст"
TITLE2 = "Поставка бумаги для офисной техники"


def listing():
    return (f"<html><body><a href='https://torgi.etpsp.ru/procedure/foreign'>Внешний лот</a>"
            f"<a href='/procedures/?procedure={SLUG1}'>{TITLE1}</a>"
            f"<a href='/procedures?procedure={SLUG2}'>{TITLE2}</a></body></html>").encode()


def detail(number, title):
    return f"<html><main>№ {number}М 44-ФЗ<h1>{title}</h1>НМЦ Не указана</main></html>".encode()


def test_native_catalog_filters_foreign_syndicated_platforms():
    rows = parse_list(listing())
    assert len(rows) == 2
    assert [r[1] for r in rows] == ["20261000009", "20261000008"]
    assert all(r[3].startswith("https://" + HOST + "/procedures?procedure=") for r in rows)
    assert all("torgi.etpsp" not in r[3] for r in rows)


@pytest.mark.parametrize("href", [
    "https://torgi.etpsp.ru/procedures?procedure=" + SLUG1,
    "https://evil.invalid/procedures?procedure=" + SLUG1,
    "http://" + HOST + "/procedures?procedure=" + SLUG1,
    "https://" + HOST + ".evil.test/procedures?procedure=" + SLUG1,
    "/procedures?procedure=" + SLUG1 + "&other=1",
    "/procedures?procedure=" + SLUG1 + "#fragment",
    "/procedures?procedure=" + SLUG1 + "%0A",
    "/procedures?procedure=../../" + SLUG1,
    "//evil.test/procedures?procedure=" + SLUG1,
])
def test_foreign_or_malformed_urls_fail_closed(href):
    assert safe_slug(href) is None


def test_visible_number_and_title_confirmed_separately():
    row = parse_list(listing())[0]
    result = verify_detail(detail("20261000009",TITLE1),slug=row[0],identity=row[1],title=row[2])
    assert result["identity"] == "20261000009"
    assert result["number_confirmed"]
    with pytest.raises(ValueError):
        verify_detail(detail("20261000008",TITLE1),slug=row[0],identity=row[1],title=row[2])
    with pytest.raises(ValueError):
        verify_detail(detail("20261000009","Some unrelated listing"),slug=row[0],identity=row[1],title=row[2])
    with pytest.raises(ValueError):
        verify_detail(b"<h1>" + TITLE1.encode() + b"</h1>",slug=row[0],identity=row[1],title=row[2])


def test_no_unverified_cards_accepted():
    with pytest.raises(ValueError):
        parse_list(b"<html><a href='https://torgi.etpsp.ru/abc'>foreign</a></html>")
    with pytest.raises(ValueError):
        parse_list(listing(),limit=3)



def test_native_source_fetches_only_first_party_detail_pages(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    import app.sources.nmck_native_public as target
    urls = []
    SLUGS = [SLUG1, SLUG2]
    def response(body):
        return SimpleNamespace(content=body, headers={"content-type":"text/html; charset=utf-8"},raise_for_status=lambda:None)
    class Fake:
        async def get(self, url):
            urls.append(url)
            if url == LIST_URL:
                return response(listing())
            if "?procedure=" not in url:
                raise AssertionError("Unexpected remote URL")
            slug = url.split("?procedure=",1)[1]
            if slug not in SLUGS:
                raise AssertionError("Disallowed or foreign ID")
            idx = SLUGS.index(slug)
            return response(detail(["20261000009","20261000008"][idx], [TITLE1,TITLE2][idx]))
    @asynccontextmanager
    async def client(**kw):
        assert kw["trust_env"] is False and kw["follow_redirects"] is False
        yield Fake()
    monkeypatch.setattr(target,"source_client",client)
    rows=asyncio.run(NmckNativePublicSource().fetch(limit=2))
    assert len(rows)==2
    assert [i.external_id for i in rows]==["20261000009","20261000008"]
    assert rows[0].tender_number=="20261000009М"
    assert rows[0].initial_price is None
    assert urls==[LIST_URL,*[LIST_URL+"?procedure="+s for s in SLUGS]]
