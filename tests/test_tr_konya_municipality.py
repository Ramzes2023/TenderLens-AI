"""Konya official municipal original source: adversarial parser and deadline contracts."""
from datetime import datetime, timedelta, timezone
from html import escape
import asyncio
import pytest

from app.sources.eis_rss import SourceError
from app.sources.tr_konya_municipality import (
    SOURCE_ID, INDEX_URL, KonyaMunicipalitySource,
    original_detail_links, parse_original_detail,
)
from app.sources.opportunities import validate_notice

TRT = timezone(timedelta(hours=3))
NOW = datetime(2026, 10, 18, 15, tzinfo=TRT)
URL = "https://www.konya.bel.tr/ihale/standart-ctp-cam-elyaf-takviyeli-polyester-yol-kenar-dikmesi-yapim-isi"
ALTERNATE = "https://www.konya.bel.tr/ihale/hocafakih-caddesi-kopru-genisletilmesi-yapim-isi"
ICB = "https://www.konya.bel.tr/ihale/procurement-of-goods-and-related-services-for-4-electrical-multiple-units-16-cars-for-konya-commuter-operation-project"
TITLE = "Standart Ctp (Cam Elyaf Takviyeli Polyester) Yol Kenar Dikmesi Yapım İşi"
BUYER = "ULAŞIM DAİRESİ BAŞKANLIĞI"
KIK = "2026/1905251"


def index(*links):
    return ("<html><h1>İhaleler</h1>" +
            "".join('<a href="' + escape(s, quote=True) + '">İhale Konusu</a>' for s in links)
            + "</html>").encode("utf-8")


def detail(title=TITLE, kik=KIK, due="28.10.2026 - 11:00", buyer=BUYER):
    return (("<html><h1>İhale Detay</h1><div>Arama Yap</div><h2>"
             + escape(title) + "</h2><div>İhale Sahibi : " + escape(buyer)
             + "</div><div>İhalenin Yapılacağı Yer : Konya</div>"
             "<div>Son Müracaat Tarihi : " + escape(due) + "</div>"
             "<p>İhale Kayıt Numarası (İKN) : " + escape(kik) + "</p>"
             "<div>KONYA BÜYÜKŞEHİR BELEDİYE BAŞKANLIĞI tarafından teklifler EKAP üzerinden alınacaktır.</div>"
             "</html>")).encode("utf-8")


def test_real_original_list_only_and_excludes_property_and_conflicted_icb():
    links = original_detail_links(index(
        "https://evil.example/ihale/fake-original-government",
        "http://www.konya.bel.tr/ihale/fake-original-government",
        "https://www.konya.bel.tr/ihale/gayrimenkul-satis-ihale-ilani-2026",
        ICB, URL, ALTERNATE), limit=2)
    assert links == (URL, ALTERNATE)


def test_exact_original_kik_buyer_and_active_timezone_aware_deadline():
    result = parse_original_detail(detail(), link=URL, as_of=NOW)
    assert result is not None
    validate_notice(result, SOURCE_ID)
    assert result.external_id == "2026-1905251"
    assert result.tender_number == KIK and result.url == URL
    assert result.title == TITLE and result.customer == BUYER
    assert result.deadline == "2026-10-28T11:00:00+03:00"
    assert result.initial_price is None and result.currency is None and result.published_at is None


@pytest.mark.parametrize("url", [
    "https://www.konya.bel.tr.evil.test/ihale/standart-ctp-cam-elyaf-takviyeli-polyester-yol-kenar-dikmesi-yapim-isi",
    "http://www.konya.bel.tr/ihale/standart-ctp-cam-elyaf-takviyeli-polyester-yol-kenar-dikmesi-yapim-isi",
    "https://www.konya.bel.tr:444/ihale/standart-ctp-cam-elyaf-takviyeli-polyester-yol-kenar-dikmesi-yapim-isi",
    URL + "?token=x", URL + "#ignored",
])
def test_reject_url_origin_and_query_tricks(url):
    with pytest.raises(SourceError):
        parse_original_detail(detail(), link=url, as_of=NOW)


def test_missing_or_expired_or_invalid_original_record_never_stored():
    assert parse_original_detail(detail(due="01.10.2026 - 11:00"), link=URL, as_of=NOW) is None
    assert parse_original_detail(detail(kik="not-a-kik"), link=URL, as_of=NOW) is None
    assert parse_original_detail(detail(buyer=""), link=URL, as_of=NOW) is None
    assert parse_original_detail(detail(title="GAYRİMENKUL SATIŞ İHALE İLANI"), link=URL, as_of=NOW) is None
    assert parse_original_detail(detail(due="28.14.2026 - 11:00"), link=URL, as_of=NOW) is None
    with pytest.raises(ValueError):
        parse_original_detail(detail(), link=URL, as_of=datetime(2026,10,18))


def test_no_source_no_records_or_script_instead_of_original_detail():
    with pytest.raises(SourceError):
        original_detail_links(b"<html>JS shell</html>")
    with pytest.raises(SourceError):
        original_detail_links(index("https://another.example/ihale/not-official-link"))
    with pytest.raises(SourceError):
        parse_original_detail(b"<html><h1>Generic website</h1></html>", link=URL, as_of=NOW)


def test_own_real_list_to_independent_detail_network_contract(monkeypatch):
    import app.sources.tr_konya_municipality as module
    calls=[]
    async def fake_fetch(url, timeout, accept):
        calls.append(url)
        if url == INDEX_URL:
            return index(URL, ALTERNATE)
        if url == URL:
            return detail()
        if url == ALTERNATE:
            return detail(title="Hocafakıh Caddesi Köprü Genişletilmesi Yapım İşi",
                          kik="2026/1970004", buyer="YAPI KONTROL DAİRESİ BAŞKANLIĞI",
                          due="03.11.2026 - 11:30")
        raise AssertionError("Unexpected network URL")
    monkeypatch.setattr(module, "_fetch", fake_fetch)
    monkeypatch.setattr(module, "datetime", type("Now", (), {
        "now": staticmethod(lambda tz: NOW),
        "strptime": staticmethod(datetime.strptime),
    }))
    notices=asyncio.run(KonyaMunicipalitySource().fetch(limit=2))
    assert len(notices)==2
    assert {x.tender_number for x in notices} == {KIK, "2026/1970004"}
    assert calls == [INDEX_URL, URL, ALTERNATE]
