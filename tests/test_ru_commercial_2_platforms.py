"""Offline security checks; never interpreted as real-source acceptance."""
import pytest
from scripts.research_ru_commercial_2_platforms import (
    canonical_card, listing_cards, verify_detail, PLATFORMS,
)

HOST = PLATFORMS["torgi_online"][0]
KEY1 = "Scorebofs002080000pptblbe68ttnk2o"
KEY2 = "Scorebofs002080000pnf2mlu9ke87ol8"
def href(key):
    return "/app/OfferCard/page?OfferCard.offerUUID=" + key

def source_listing():
    return (f'<a href="{href(KEY1)}">0436126002DP - Комплекс работ по устройству фасадов</a>'
            f'<a href="{href(KEY2)}">0422526001DP - Услуги по перевозке грузов в феврале</a>'
            f'<a href="https://external.invalid/app/OfferCard/page?OfferCard.offerUUID={KEY1}">'
            '0999926001DP - Внешняя закупка</a>').encode()

def detail(number, title, section="Коммерческая закупка", extra=""):
    return (f"<html><h1>Закупка {number}</h1><div>Номер процедуры {number}</div>"
            f"<div>Наименование закупки {title}</div><div>{section}</div>{extra}</html>").encode()

def test_two_distinct_official_links_with_visible_native_numbers():
    rows=listing_cards(source_listing(), HOST)
    assert len(rows)==2
    assert [x[0] for x in rows]==["0436126002DP","0422526001DP"]
    assert all(x[2].startswith("https://"+HOST+"/app/OfferCard/page?") for x in rows)

@pytest.mark.parametrize("url",[
    "https://evil.example/app/OfferCard/page?OfferCard.offerUUID="+KEY1,
    "http://"+HOST+href(KEY1),
    "https://"+HOST+".evil.example"+href(KEY1),
    href(KEY1)+"&token=1",
    href(KEY1)+"#x",
    href(KEY1).replace("Score","../Score"),
    href(KEY1).replace("page","page;jsessionid=stolen"),
    "https://foo:bar@"+HOST+href(KEY1),
    "//evil.example"+href(KEY1),
])
def test_insecure_or_foreign_urls_not_followed(url):
    assert canonical_card(HOST,url) is None

def test_official_number_and_title_independent_and_eis_mirrors_rejected():
    number,title,url=listing_cards(source_listing(),HOST)[0]
    assert verify_detail(detail(number,title),HOST,number,title,url)==(number,title,url)
    for bad in [
        detail("0999926001DP",title),
        detail(number,"Другая коммерческая закупка"),
        detail(number,title,"Закупка 223-ФЗ"),
        detail(number,title,extra="<p>Реестровый номер 32616184543 ЕИС</p>"),
        f"<script>Номер процедуры {number}; Наименование закупки {title}; Коммерческая закупка</script>".encode(),
    ]:
        with pytest.raises(ValueError):
            verify_detail(bad,HOST,number,title,url)

def test_empty_listing_never_grants_green():
    with pytest.raises(ValueError):
        listing_cards("<html><a href='/search'>Поиск</a></html>".encode("utf-8"),HOST)
