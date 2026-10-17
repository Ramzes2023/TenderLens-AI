import pytest
from app.sources.roseltorg_public_research import parse_roseltorg_public_detail

URL = "https://www.roseltorg.ru/procedure/0131100015825000054"
TITLE = "Услуги по доставке и вручению почтовых отправлений"
HTML = f"""<html><head><title>Пример</title></head><body>
<h1>Процедура: 0131100015825000054</h1>
<div>Наименование процедуры</div><div>{TITLE}</div>
<div>Организатор торгов</div><div>Заказчик</div>
</body></html>""".encode()

def test_exact_public_procedure_evidence():
    parsed = parse_roseltorg_public_detail(HTML, URL)
    assert parsed["external_id"] == "0131100015825000054"
    assert parsed["title"] == TITLE
    assert parsed["url"] == URL

@pytest.mark.parametrize("url", [
    "http://www.roseltorg.ru/procedure/0131100015825000054",
    "https://evil.example/procedure/0131100015825000054",
    "https://www.roseltorg.ru/procedure/0131100015825000054?redirect=1",
    "https://www.roseltorg.ru/procedure/0131100015825000054/extra",
    "https://www.roseltorg.ru@evil.example/procedure/0131100015825000054",
])
def test_refuses_unsafe_urls(url):
    with pytest.raises(ValueError):
        parse_roseltorg_public_detail(HTML, url)

def test_refuses_unverified_identity_and_title():
    with pytest.raises(ValueError):
        parse_roseltorg_public_detail(HTML.replace(b"0131100015825000054", b"0131100015825000055"), URL)
    with pytest.raises(ValueError):
        parse_roseltorg_public_detail(b"<h1>Procedure</h1>", URL)
    with pytest.raises(ValueError):
        parse_roseltorg_public_detail(HTML.replace("Наименование процедуры".encode(), b"missing"), URL)

def test_refuses_large_or_binary_payload():
    for payload in (b"", b"\x00", b"x" * 1800001, "not bytes"):
        with pytest.raises(ValueError):
            parse_roseltorg_public_detail(payload, URL)
