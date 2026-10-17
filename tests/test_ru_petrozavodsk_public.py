"""Pure local fixtures. Only hosted live source acceptance can establish reachability."""
import pytest
from scripts.research_ru_petrozavodsk_public import listing_links, verified_detail, canonical_purchase

ID_A="b205eea1-5fc6-4622-9ad2-a8e6d4c7c839"
ID_B="087b0a06-cebe-4996-935f-a3ef03cd8b1f"
TITLE_A="Поставка музыкального оборудования"
TITLE_B="Поставка спортивных товаров"

def listing():
    return (f'<a href="/purchases/{ID_A}">Закупка № 0051452025218634 {TITLE_A}</a>'
            f'<a href="/purchases/{ID_B}">{TITLE_B}</a>'
            f'<a href="https://evil.invalid/purchases/{ID_A}">Заказ вне площадки</a>').encode()

def detail(number,title):
    return f'<html><h4>Закупка № {number} {title}</h4><p>Дата публикации</p></html>'.encode()

def test_two_distinct_firstparty_canonical_urls():
    rows=listing_links(listing())
    assert len(rows)==2
    assert rows[0]==("https://eshop-ptz.ru/purchases/"+ID_A,"0051452025218634",TITLE_A)
    assert rows[1]==("https://eshop-ptz.ru/purchases/"+ID_B,None,TITLE_B)

@pytest.mark.parametrize("url",[
    "http://eshop-ptz.ru/purchases/"+ID_A,
    "https://evil.invalid/purchases/"+ID_A,
    "https://eshop-ptz.ru.evil.invalid/purchases/"+ID_A,
    "/purchases/"+ID_A+"?session=abc",
    "/purchases/"+ID_A+"#target",
    "/purchases/"+ID_A+"/",
    "/purchases/not-a-uuid",
    "https://username@eshop-ptz.ru/purchases/"+ID_A,
    "https://eshop-ptz.ru:8443/purchases/"+ID_A,
    "//evil.invalid/purchases/"+ID_A,
])
def test_untrusted_detail_or_session_link_denied(url):
    assert canonical_purchase(url) is None

def test_detail_identity_is_independent_and_not_just_static_url():
    assert verified_detail(detail("0051452025218634",TITLE_A),"0051452025218634",TITLE_A)==("0051452025218634",TITLE_A)
    assert verified_detail(detail("0051452025218634",TITLE_A),None,TITLE_A)[0]=="0051452025218634"
    with pytest.raises(ValueError):
        verified_detail(detail("0051452025218635",TITLE_A),"0051452025218634",TITLE_A)
    with pytest.raises(ValueError):
        verified_detail(detail("0051452025218634","Другой предмет закупки"),None,TITLE_A)
    with pytest.raises(ValueError):
        verified_detail(b"<script>Закупка № 0051452025218634 Поставка музыкального оборудования</script>",None,TITLE_A)

def test_unknown_or_external_list_not_proof():
    assert listing_links(b'<a href="/notices">Поиск</a>')==[]
