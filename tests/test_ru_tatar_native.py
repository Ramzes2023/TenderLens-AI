"""Original Tatarstan DP, not EIS syndicated or login-only page."""
import pytest
from scripts.research_ru_tatar_native import canonical,list_cards,verify_detail,LIST

A="Scoreboo2k000g0000ptnukvta5r0lamo"
B="Scoreboo2k000g0000ptt4aamj2m7ifpg"
TITLE_A="Выполнение работ по созданию автоматизированной системы городской AI бот"
TITLE_B="Возведение двух нестационарных объектов Павильон"

def listing():
    return (
        f'<a href="/app/OfferCard/page?OfferCard.offerUUID={A}">{TITLE_A}</a>'
        f'<a href="/app/OfferCard/page?OfferCard.offerUUID={B}">{TITLE_B}</a>'
    ).encode("utf-8")

def detail(number,title,eis=""):
    return (f"<h1>Закупка {number}</h1><div>Номер процедуры {number}</div>"
            f"<div>Вид торговой процедуры Закупка</div>"
            f"<div>Наименование закупки {title}</div>{eis}").encode("utf-8")

def test_two_native_first_party_links_and_exact_local_dp_numbers():
    a,b=list_cards(listing())
    assert a[0]=="https://etpzakupki.tatar/app/OfferCard/page?OfferCard.offerUUID="+A
    assert verify_detail(detail("0013726018DP",TITLE_A),a[0],a[1])[0]=="0013726018DP"
    assert verify_detail(detail("0013726019DP",TITLE_B),b[0],b[1])[0]=="0013726019DP"

@pytest.mark.parametrize("v",[
    "http://etpzakupki.tatar/app/OfferCard/page?OfferCard.offerUUID="+A,
    "https://evil.test/app/OfferCard/page?OfferCard.offerUUID="+A,
    "//evil.test/app/OfferCard/page?OfferCard.offerUUID="+A,
    "https://etpzakupki.tatar.evil.test/app/OfferCard/page?OfferCard.offerUUID="+A,
    "/app/OfferCard/page?OfferCard.offerUUID="+A+"&token=evil",
    "/app/OfferCard/page?OfferCard.offerUUID="+A+"#hash",
    "https://user:pw@etpzakupki.tatar/app/OfferCard/page?OfferCard.offerUUID="+A,
    "/app/OfferCard/page?OfferCard.offerUUID=javascript:evil",
])
def test_canonical_origin_exact_query_and_token_only(v):
    assert canonical(v) is None

def test_mirrored_223_fz_eis_excluded_without_duplicating_original():
    url,title=list_cards(listing())[0]
    with pytest.raises(ValueError):
        verify_detail(detail("0013726018DP",title,"Реестровый номер 32616207848 ЕИС"),url,title)
    with pytest.raises(ValueError):
        verify_detail(detail("32616207848",title),url,title)
    with pytest.raises(ValueError):
        verify_detail(detail("0013726018DP","Другой предмет"),url,title)
    with pytest.raises(ValueError):
        verify_detail(f"<script>Номер процедуры 0013726018DP Вид торговой процедуры Закупка Наименование закупки {title}</script>".encode(),url,title)

def test_empty_listing_cannot_pass():
    with pytest.raises(ValueError):
        list_cards(b"<html>Search no public detail links</html>")
