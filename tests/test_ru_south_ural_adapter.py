"""Synthetic HTML is NEVER accepted as live procurement proof."""
import pytest
from app.sources.south_ural_public import canonical_detail,parse_public_listing,verify_public_detail,LIST_URL,SouthUralPublicSource

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
        parse_public_listing("<html><a href='/login'>Личный кабинет</a></html>".encode("utf-8"))
    with pytest.raises(ValueError):
        parse_public_listing(rows().replace(b"109627",b"109631"))



def test_public_adapter_only_follows_first_party_real_number_and_title(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    import app.sources.south_ural_public as module
    matching={t[2]:page(t[0],t[1]) for t in parse_public_listing(rows())}
    urls=[]
    class FakeClient:
        async def get(self,url):
            urls.append(url)
            data=rows() if url==LIST_URL else matching[url]
            return SimpleNamespace(content=data,headers={"content-type":"text/html"},raise_for_status=lambda:None)
    @asynccontextmanager
    async def fake_client(**kw):
        assert kw["trust_env"] is False and kw["follow_redirects"] is False
        yield FakeClient()
    monkeypatch.setattr(module,"source_client",fake_client)
    notices=asyncio.run(SouthUralPublicSource().fetch(limit=2))
    assert [n.external_id for n in notices]==["109631","109627"]
    assert all(n.region=="Челябинская область" and n.initial_price is None and n.deadline is None for n in notices)
    assert urls==[LIST_URL,*matching]


def test_collect_up_to_ten_distinct_current_public_invites():
    from app.sources.south_ural_public import parse_public_listing, MAX_PAGE_ITEMS
    cards = []
    for i in range(12):
        n = 109600 + i
        cards.append(
            f'<tr><td>Прием оферт</td><td>{n}</td>'
            f'<td><a href="/Market/OfferInvitationOpen/View/{n}?isReadOnly=True">'
            f'Закупка офисных товаров номер {n}</a></td></tr>'
        )
    body = ("<table>" + "".join(cards) + "</table>").encode("utf-8")
    assert len(parse_public_listing(body)) == MAX_PAGE_ITEMS == 10
    assert [row[0] for row in parse_public_listing(body)] == [str(109600 + n) for n in range(10)]
    with pytest.raises(ValueError):
        parse_public_listing(body, limit=100)
    with pytest.raises(ValueError):
        parse_public_listing(body, limit=True)



def test_regional_detail_metadata_is_precise_and_never_invented():
    from app.sources.south_ural_public import public_detail_metadata
    extra = """<table><tr><td>Организация:</td><td>МБУ ШКОЛА № 7 Г. ЧЕЛЯБИНСКА</td></tr>
    <tr><td>Максимальная цена товаров, работ, услуг*</td><td>29 000,00</td></tr>
    <tr><td>Валюта</td><td>Российский рубль</td></tr>
    <tr><td>Дата окончания подачи оферт*</td>
    <td>17.07.2026 08:00 (UTC+05:00) Екатеринбург</td></tr></table>""".encode("utf-8")
    assert public_detail_metadata(extra) == {
        "customer": "МБУ ШКОЛА № 7 Г. ЧЕЛЯБИНСКА",
        "initial_price": 29000.0,
        "currency": "RUB",
        "deadline": "2026-07-17T08:00:00+05:00",
    }
    assert public_detail_metadata(b"<table></table>") == {
        "customer": None, "initial_price": None,
        "currency": None, "deadline": None,
    }


def test_unpublished_amount_not_invented_or_assumed_zero():
    from app.sources.south_ural_public import public_detail_metadata
    undecided = "<tr><td>Максимальная цена товаров, работ, услуг*</td><td>Цена не определена</td></tr>"
    x = public_detail_metadata(undecided.encode())
    assert x["initial_price"] is None and x["currency"] is None
    bad = "<tr><td>Максимальная цена товаров, работ, услуг*</td><td>29.000 RUB</td></tr>"
    with pytest.raises(ValueError):
        public_detail_metadata(bad.encode())


def test_duplicate_conflicting_detail_metadata_rejected():
    from app.sources.south_ural_public import public_detail_metadata
    body = """<tr><td>Организация:</td><td>Заказчик А</td></tr>
        <tr><td>Организация:</td><td>Заказчик Б</td></tr>""".encode("utf-8")
    with pytest.raises(ValueError):
        public_detail_metadata(body)


def test_metadata_only_after_independently_verified_firstparty_detail(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    import app.sources.south_ural_public as module
    original = parse_public_listing(rows())
    list_by_url = {x[2]: x for x in original}
    def detail_html(n,t):
        return (page(n,t).decode("utf-8") + """<table>
        <tr><td>Организация:</td><td>МБУ ШКОЛА № 7</td></tr>
        <tr><td>Максимальная цена товаров, работ, услуг*</td><td>8 990,50</td></tr>
        <tr><td>Валюта</td><td>Российский рубль</td></tr>
        <tr><td>Дата окончания подачи оферт*</td><td>31.10.2026 13:00 (UTC+05:00) Екатеринбург</td></tr>
        </table>""").encode("utf-8")
    class Fake:
        async def get(self,url):
            body=rows() if url==LIST_URL else detail_html(list_by_url[url][0],list_by_url[url][1])
            return SimpleNamespace(content=body,headers={"content-type":"text/html"},raise_for_status=lambda:None)
    @asynccontextmanager
    async def session(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        yield Fake()
    monkeypatch.setattr(module,"source_client",session)
    notices=asyncio.run(module.SouthUralPublicSource().fetch(limit=2))
    assert len(notices)==2
    assert all(n.customer=="МБУ ШКОЛА № 7" and n.initial_price==8990.5 and n.currency=="RUB"
               and n.deadline=="2026-10-31T13:00:00+05:00" for n in notices)
