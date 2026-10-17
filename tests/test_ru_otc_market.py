"""Pure hostile test fixtures, never accepted as live source evidence."""
import pytest
from scripts.research_ru_otc_market import canonical,list_native,verify_detail,LIST_URL

def listing():
    return ('''<a href="/ProductRequestGroup/Index/1224531">Срочная закупка 1224531-25VLGR Поставка бумаги офисной</a>
<a href="/ProductRequestGroup/Index/1223594">Закупка 1223594-25VLGR Выполнение работ по монтажу СОУЭ</a>
<a href="https://evil.test/ProductRequestGroup/Index/1999999">Закупка 1999999 Поставка мебели</a>''').encode()

def detail(number,title):
    return (f"<h1>Закупка №{number}. {title}</h1><div>Закупка №{number}</div>"
            f"<table><tr><td>Номер Закупки</td><td>{number}</td></tr>"
            f"<tr><td>Наименование Закупки</td><td>{title}</td></tr></table>").encode()

def test_two_public_list_original_ids():
    out=list_native(listing())
    assert [x[0] for x in out]==["1224531","1223594"]
    assert [x[2] for x in out]==[
        "https://market.otc.ru/ProductRequestGroup/Index/1224531",
        "https://market.otc.ru/ProductRequestGroup/Index/1223594",
    ]

@pytest.mark.parametrize("url",[
    "https://market.otc.ru.evil.test/ProductRequestGroup/Index/1224531",
    "http://market.otc.ru/ProductRequestGroup/Index/1224531",
    "https://wrong.test/ProductRequestGroup/Index/1224531",
    "/ProductRequestGroup/Index/1224531?session=abc",
    "/ProductRequestGroup/Index/1224531#x",
    "/ProductRequestGroup/Index/1224531/../admin",
    "//evil.test/ProductRequestGroup/Index/1224531",
    "https://user:pw@market.otc.ru/ProductRequestGroup/Index/1224531",
])
def test_unsafe_url_rejected(url):
    assert canonical(url) is None

def test_external_mirror_and_fake_detail_cannot_go_green():
    n,t,u=list_native(listing())[0]
    assert verify_detail(detail(n,t),n,t,u)==(n,t,u)
    for bad in [
        detail("1224532",t),
        detail(n,"Поставка цемента"),
        detail(n,t).replace(b"<td>1224531</td>",b"<td>1000000</td>"),
        "<script>Закупка №1224531 Поставка бумаги офисной Номер Закупки 1224531</script>".encode(),
    ]:
        with pytest.raises(ValueError):
            verify_detail(bad,n,t,u)
    with pytest.raises(ValueError):
        list_native('<a href="/login">Вход</a>'.encode())
