"""Synthetic HTML is NEVER accepted as live procurement proof."""
import pytest
from scripts.research_ru_south_ural_public import canonical_detail,parse_public_listing,verify_public_detail,LIST_URL

def rows():
    return """<html><table>
<tr><td>Прием оферт</td><td>109631</td><td>Запрос коммерческих предложений</td>
<td><a href="/Market/OfferInvitationOpen/View/109631?isReadOnly=True&amp;returnUrl=%2FMarket%2FOfferInvitationOpen">Изготовление и поставка ежедневников</a></td>
<td>МБУ КОМПАС</td></tr>
<tr><td>Прием оферт</td><td>109627</td><td>Закупка малого объема по 44-ФЗ</td>
<td><a href="/Market/OfferInvitationOpen/View/109627?isReadOnly=True">Оказание услуг связи</a></td><td>МКУ ЭВИС</td></tr>
</table></html>""".encode()

def page(number,title,type_name="Закупка на основании пункта 4 части 1 статьи 93 44-ФЗ"):
    return (f"""<h2>Опубликованные закупки - Просмотр приглашения № {number}</h2>
    <table><tr><td>Номер*</td><td>{number}</td></tr>
    <tr><td>Предмет договора*</td><td>{title}</td></tr>
    <tr><td>Тип закупки*</td><td>{type_name}</td></tr></table>""").encode()

def test_two_genuine_firstparty_numbered_rows():
    out=parse_public_listing(rows())
    assert [r[0] for r in out]==["109631","109627"]
    assert out[0][2]=="https://www.vendorportal.ru/Market/OfferInvitationOpen/View/109631?isReadOnly=True"

@pytest.mark.parametrize("href",[
    "http://www.vendorportal.ru/Market/OfferInvitationOpen/View/109631",
    "https://evil.test/Market/OfferInvitationOpen/View/109631",
    "https://www.vendorportal.ru.evil.test/Market/OfferInvitationOpen/View/109631",
    "/Market/OfferInvitationOpen/View/109631#fragment",
    "/Market/OfferInvitationOpen/View/109631;jsessionid=evil",
    "/Market/OfferInvitationOpen/View/109631/../evil",
    "//evil.test/Market/OfferInvitationOpen/View/109631",
    "https://user:password@www.vendorportal.ru/Market/OfferInvitationOpen/View/109631"
])
def test_no_unapproved_href(href):
    assert canonical_detail(href) is None

def test_independent_detail_checks():
    n,t,url=parse_public_listing(rows())[0]
    assert verify_public_detail(page(n,t),n,t,url)==(n,t,url)
    for bad in [
        page("109999",t),
        page(n,"Неправильный предмет"),
        page(n,t,type_name="Страница поддержки"),
        f"<script>Просмотр приглашения № {n} Номер {n} Предмет договора {t} Тип закупки Закупка</script>".encode(),
    ]:
        with pytest.raises(ValueError):
            verify_public_detail(bad,n,t,url)

def test_no_green_on_missing_list_or_duplicate_id():
    with pytest.raises(ValueError):
        parse_public_listing(b"<html><a href='/login'>Личный кабинет</a></html>")
    with pytest.raises(ValueError):
        parse_public_listing(rows().replace(b"109627",b"109631"))
