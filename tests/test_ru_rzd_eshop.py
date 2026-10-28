import pytest
from scripts.research_ru_rzd_eshop import canonical,listed_purchases,independently_verified_detail

def list_html():
    return """<a href="/purchases/e9980393-b507-4062-9991-f0020338ba87">Поставка оформленных букетов из живых цветов /№ 227114</a>
<a href="/purchases/b205eea1-5fc6-4622-9ad2-a8e6d4c7c839">Поставка офисной мебели /№ 239915</a>
<a href="https://evil.test/purchases/e9980393-b507-4062-9991-f0020338ba87">Подложная закупка</a>""".encode("utf-8")
def detail(n,title):
    return f"<h2>Ценовой запрос № {n} {title}</h2><p>Подача оферт до</p>".encode("utf-8")

def test_two_distinct_independent_public_links():
    rows=listed_purchases(list_html())
    assert len(rows)==2
    assert rows[0][1]=="Поставка оформленных букетов из живых цветов"
    assert rows[1][1]=="Поставка офисной мебели"
    assert rows[0][0]=="https://eshoprzd.ru/purchases/e9980393-b507-4062-9991-f0020338ba87"

@pytest.mark.parametrize("href",[
    "http://eshoprzd.ru/purchases/e9980393-b507-4062-9991-f0020338ba87",
    "https://evil.test/purchases/e9980393-b507-4062-9991-f0020338ba87",
    "//evil.test/purchases/e9980393-b507-4062-9991-f0020338ba87",
    "https://eshoprzd.ru.evil.test/purchases/e9980393-b507-4062-9991-f0020338ba87",
    "/purchases/e9980393-b507-4062-9991-f0020338ba87?session=abc",
    "/purchases/e9980393-b507-4062-9991-f0020338ba87#frag",
    "/purchases/e9980393-b507-4062-9991-f0020338ba87/",
    "https://user@eshoprzd.ru/purchases/e9980393-b507-4062-9991-f0020338ba87",
    "/purchases/../../etc",
])
def test_untrusted_origin_or_session_never_passes(href):
    assert canonical(href) is None

def test_original_heading_number_and_title_required():
    url,title=listed_purchases(list_html())[0]
    assert independently_verified_detail(detail("227114",title),url,title)==("227114",title,url)
    for bad in [
        detail("227114","Несовпадающая закупка"),
        '<script><h2>Ценовой запрос № 227114 Поставка оформленных букетов из живых цветов</h2></script>'.encode("utf-8"),
        '<h2>Ценовой запрос № 227114 Поставка оформленных букетов из живых цветов</h2><h2>Ценовой запрос № 227115 Поставка оформленных букетов из живых цветов</h2>'.encode("utf-8"),
    ]:
        with pytest.raises(ValueError):
            independently_verified_detail(bad,url,title)

def test_no_fake_listing():
    with pytest.raises(ValueError):
        listed_purchases("<html>Поставка товара № 239915</html>".encode("utf-8"))
