"""Synthetic fixtures are only contract tests, never live source proof."""
import pytest
from scripts.research_ru_spb_estore_public import canonical, listing, validate_detail, INDEX

def public_list():
    return ("""<table>
<tr><td>Поставка хозяйственных товаров лот 2</td><td>2026006227057</td>
<td><a href="/electronicshop/procedure/form/view/817094/">Поставка стендов информационных</a></td></tr>
<tr><td>Поставка услуг</td><td>2026006223290</td>
<td><a href="/electronicshop/procedure/form/view/817628/">Поставка вала карданного раздвижного</a></td></tr>
<tr><td>Поставка иных товаров</td><td>2026006227058</td>
<td><a href="https://bad.example/electronicshop/procedure/form/view/817628/">Поддельная внешняя закупка</a></td></tr></table>""").encode("utf-8")

def public_detail(number,title):
    return f"<main><h1>Общие сведения о закупке</h1><p>Регистрационный номер {number}</p><p>Объект закупки: {title}</p></main>".encode("utf-8")

def test_strict_two_original_source_records():
    records=listing(public_list())
    assert len(records)==2
    assert [x[0] for x in records]==["2026006227057","2026006223290"]
    assert records[0][2]=="https://estore.gz-spb.ru/electronicshop/procedure/form/view/817094/"

@pytest.mark.parametrize("url",[
    "http://estore.gz-spb.ru/electronicshop/procedure/form/view/817094/",
    "https://estore.gz-spb.ru.evil.test/electronicshop/procedure/form/view/817094/",
    "https://bad.example/electronicshop/procedure/form/view/817094/",
    "//bad.example/electronicshop/procedure/form/view/817094/",
    "/electronicshop/procedure/form/view/817094/?token=1",
    "/electronicshop/procedure/form/view/817094/#fragment",
    "/electronicshop/procedure/form/view/817094/../../other",
    "/electronicshop/procedure/form/view/817094;session=1/",
])
def test_reject_untrusted_reference(url):
    assert canonical(url) is None

def test_details_must_match_original_independent_numbers_and_titles():
    number,title,url=listing(public_list())[0]
    assert validate_detail(public_detail(number,title),number,title,url)==(number,title,url)
    for page in (public_detail("2026006227058",title),
                 public_detail(number,"Чужой предмет закупки"),
                 f"<script>Объект закупки: {title}; Регистрационный номер {number}</script>".encode("utf-8")):
        with pytest.raises(ValueError):
            validate_detail(page,number,title,url)

def test_empty_no_fake_success():
    with pytest.raises(ValueError):
        listing(b"<a href='/login'>Only login</a>")
