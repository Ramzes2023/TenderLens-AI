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



def test_south_ural_optin_flag_never_activates_unrequested_production_adapter():
    from app.monitoring.config import MonitoringSettings
    from app.sources.catalog import build_source_catalog
    disabled = build_source_catalog(MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=2,
        max_notifications_per_cycle=2, request_timeout=20,
        eis_rss_urls=(), ca_bundle_file=None,
        profile_feeds_enabled=False,
    ))
    assert "south_ural_public" not in disabled.enabled_keys
    enabled = build_source_catalog(MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=2,
        max_notifications_per_cycle=2, request_timeout=20,
        eis_rss_urls=(), ca_bundle_file=None,
        profile_feeds_enabled=False,
        south_ural_public_enabled=True,
    ))
    assert "south_ural_public" in enabled.enabled_keys
    assert enabled.registry.get("south_ural_public").source.name == "south_ural_public"


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



def test_official_detail_deadline_requires_actual_number_title_and_utc_offset():
    from app.sources.south_ural_public import independently_verified_deadline
    n,t,url=parse_public_listing(rows())[0]
    good=page(n,t).replace(
        b"</table>",
        '<tr><td>Дата окончания подачи оферт*</td><td>23.10.2026 10:00 (UTC+05:00) Екатеринбург</td></tr></table>'.encode("utf-8"),
    )
    assert independently_verified_deadline(good,n,t,url) == "2026-10-23T10:00:00+05:00"
    assert independently_verified_deadline(page(n,t),n,t,url) is None
    for bad in [
        good.replace(b"UTC+05:00", b"UTC+16:00"),
        good.replace(b"UTC+05:00", b"UTC+05:99"),
        good.replace(b"23.10.2026", b"32.10.2026"),
        good.replace(b"23.10.2026", b"23.10.2026<script>alert(1)</script>"),
        good.replace(b"109631",b"109632"),
    ]:
        with pytest.raises(ValueError):
            independently_verified_deadline(bad,n,t,url)


def test_deadline_from_malicious_unrelated_script_is_never_used():
    from app.sources.south_ural_public import independently_verified_deadline
    n,t,url=parse_public_listing(rows())[0]
    fake=page(n,t)+'<script>Date: 24.10.2026 20:00 (UTC+05:00) Екатеринбург</script>'.encode('utf-8')
    assert independently_verified_deadline(fake,n,t,url) is None
