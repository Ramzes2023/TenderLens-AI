import pytest
from scripts.research_ru_stan_commercial import parse_list, canonical, verify_detail, LIST_URL

def listing():
    return ('''<a href="/etp/AAaaBB12">№ 32616478602 / АЭ-2026-000033</a>
<a href="/etp/AAaaBB12">Поставка угля каменного для нужд предприятия</a>
<a href="/etp/RScxkWBC">№ ЗК-2026-000020</a>
<a href="/etp/RScxkWBC"><h2>Поставка пожарных шкафов</h2></a>
<a href="/etp/Aabbcc12">№ ЗК-2026-000016</a>
<a href="/etp/Aabbcc12">Строительно-монтажные работы по водоснабжению</a>
<a href="https://outside.example/etp/Abcdef12">№ ЗК-2026-000099</a>''').encode()

def detail(n,t,section="Коммерческая закупка"):
    return f"<div>{section}</div><h1>{t}</h1><div>Номер процедуры</div><div>{n}</div>".encode()

def test_first_party_commercial_two_links_not_eis_mirrors():
    r=parse_list(listing())
    assert len(r)==2
    assert [x[0] for x in r]==["ЗК-2026-000020","ЗК-2026-000016"]
    assert all(x[2].startswith(LIST_URL+"/") for x in r)

@pytest.mark.parametrize("url",[
    "https://evil.example/etp/RScxkWBC",
    "http://stantorgi.ru/etp/RScxkWBC",
    "https://stantorgi.ru.evil.test/etp/RScxkWBC",
    "/etp/RScxkWBC?secret=1",
    "/etp/RScxkWBC#secret",
    "/etp/../../etc",
    "//evil.test/etp/RScxkWBC"])
def test_untrusted_urls_never_accepted(url):
    assert canonical(url) is None

def test_one_real_commercial_candidate_among_eis_mirrors():
    page = ('''<a href="/etp/AAaaBB12">№ 32616478602 / АЭ-2026-000033</a>
<a href="/etp/AAaaBB12">Поставка угля каменного для нужд предприятия</a>
<a href="/etp/RScxkWBC">№ ЗК-2026-000020</a>
<a href="/etp/RScxkWBC"><h2>Поставка пожарных шкафов</h2></a>''').encode()
    cards = parse_list(page)
    assert len(cards) == 1
    assert cards[0][0] == "ЗК-2026-000020"
    assert verify_detail(detail(cards[0][0], cards[0][1]), *cards[0]) == cards[0]


def test_independent_title_and_number_required():
    n,t,u=parse_list(listing())[0]
    assert verify_detail(detail(n,t),n,t,u)==(n,t,u)
    for bad in (detail("ЗК-2026-000021",t),detail(n,"Другая процедура"),
                detail(n,t,"Закупка по 223-ФЗ"),f"<h1>{t}</h1><script>Номер процедуры {n} Коммерческая закупка</script>".encode()):
        with pytest.raises(ValueError):
            verify_detail(bad,n,t,u)

def test_fail_closed_on_eis_only():
    with pytest.raises(ValueError):
        parse_list('<a href="/etp/AAaaBB12">№ 32616478602 / АЭ-2026-000033</a>'.encode('utf-8'))
