"""Offline adversarial GPB Gos44 originals: NOT live tender evidence."""
import pytest

from scripts.research_ru_gpb_gos_html_originals import (
    HOST, ORIGINALS, verify_official_original,
)


def original(number):
    return (
        f"<html><body><h1>Сведения о процедуре ЭА {number}</h1>"
        f"<div>Общая информация о закупке</div>"
        f"<p>Номер извещения {number}</p>"
        "<p>Наименование объекта закупки</p>"
        "<p>Оборудование для муниципального учреждения</p>"
        "</body></html>"
    ).encode("utf-8")


def test_fixed_published_first_party_links_and_distinct_eis_numbers():
    assert HOST == "gos.etpgpb.ru"
    assert len(ORIGINALS) == 2
    assert len({num for _, num in ORIGINALS}) == 2
    assert all(url.startswith(f"https://{HOST}/front/procedure/view/")
               and "?" not in url for url, _ in ORIGINALS)


def test_bounded_offline_visible_original_parser():
    number = ORIGINALS[0][1]
    assert verify_official_original(original(number), number)


@pytest.mark.parametrize("wrong", [
    b"", b"<html>Login</html>",
    b"<html><script>0891200000626010069</script></html>",
    b"<html><p>Номер извещения 0891200000626010069</p></html>",
    b"<html><p>Сведения о процедуре</p></html>",
    original("0358100002226000213"),
    original("0891200000626010069") + b"x" * 2_200_000,
])
def test_reject_html_login_hidden_or_mismatching_notices(wrong):
    with pytest.raises(ValueError):
        verify_official_original(wrong, ORIGINALS[0][1])
