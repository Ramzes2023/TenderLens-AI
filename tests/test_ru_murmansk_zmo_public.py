"""Only strict offline parser checks; network must pass independently in hosted CI."""
import pytest
from scripts.research_ru_murmansk_zmo_public import (
    canonical, listing, verify_detail, INDEX,
)

def sample_listing():
    return """<table>
<tr><td>ИМЗ-2026-005228</td><td><a href="/site/GzwSP/Notice?noticeLink=10987727">Приобретение сетевого оборудования и аксессуаров</a></td></tr>
<tr><td>ИМЗ-2026-004890</td><td><a href="/site/GzwSP/Notice?noticeLink=10965788">Приобретение сейфов</a></td></tr>
</table>""".encode()

def detail(number, title):
    return (f"""<table>
<tr><td>Номер и дата извещения</td><td>{number} от 28.08.2026</td></tr>
<tr><td>Объект закупки</td><td>{title}</td></tr>
<tr><td>Начальная (максимальная) цена закупки, руб.</td><td>85 000.00</td></tr>
<tr><td>Заказчик</td><td>ГБУ Мурманской области</td></tr>
</table>""").encode()

def test_two_first_party_municipal_notices_and_details():
    rows = listing(sample_listing())
    assert len(rows) == 2
    assert [n[1] for n in rows] == ["ИМЗ-2026-005228", "ИМЗ-2026-004890"]
    for internal, number, title, url in rows:
        assert verify_detail(detail(number,title),internal,number,title,url) == (number,title,url)

@pytest.mark.parametrize("href", [
    "http://gz-murman.ru/site/GzwSP/Notice?noticeLink=10987727",
    "https://evil.example/site/GzwSP/Notice?noticeLink=10987727",
    "https://gz-murman.ru.evil.example/site/GzwSP/Notice?noticeLink=10987727",
    "/site/GzwSP/Notice?noticeLink=10987727&returnUrl=https://evil.example",
    "/site/GzwSP/Notice?noticeLink=10987727#fragment",
    "/site/GzwSP/Notice?noticeLink=foo",
    "/site/GzwSP/Notice?noticeLink=10987727%0d%0a",
    "/site/GzwSP/Notice?noticeLink=10987727&noticeLink=10965788",
    "https://user:pass@gz-murman.ru/site/GzwSP/Notice?noticeLink=10987727",
])
def test_reject_unapproved_source_urls(href):
    assert canonical(href) is None

def test_no_success_from_undiscovered_historic_detail_or_login():
    with pytest.raises(ValueError):
        listing(b"<html><body>Login required</body></html>")
    with pytest.raises(ValueError):
        listing(b"<a href='/site/GzwSP/Notice?noticeLink=10987727'>Historic indexed offer</a>")
    with pytest.raises(ValueError):
        listing(sample_listing().replace(b"10965788", b"10987727"))

def test_detail_requires_original_id_subject_price_and_buyer():
    internal, number, title, url = listing(sample_listing())[0]
    for altered in (
        detail("ИМЗ-2026-999999", title),
        detail(number, "Другой предмет закупки"),
        detail(number, title).replace("Начальная (максимальная) цена закупки", "Цена договора"),
        detail(number, title).replace("Заказчик", "Продавец"),
        b"<script>Номер и дата извещения ИМЗ-2026-005228 Объект закупки Приобретение сетевого оборудования и аксессуаров</script>",
    ):
        with pytest.raises(ValueError):
            verify_detail(altered,internal,number,title,url)

def test_public_source_origin_is_exact():
    assert INDEX == "https://gz-murman.ru/site/GzwSP/NoticesGrid"
