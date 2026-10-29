"""Offline adversarial tests. Fixtures are NEVER live procurement evidence."""
import pytest
from scripts.research_ru_dagestan_small_originals import (
    canonical, index_notices, detail_proof, LIST, HOST,
)


def official_synthetic_listing():
    return ("""<table>
    <tr><td><a href="/smallpurchases/GzwSP/Notice?noticeLink=10980001">Приобретение хозяйственных материалов</a></td></tr>
    <tr><td><a href="/smallpurchases/GzwSP/Notice?noticeLink=10980002">Поставка оборудования для школы</a></td></tr>
    </table>""").encode("utf-8")


def synthetic_detail(title, native="ИМЗ-2026-123456", buyer="Заказчик: ГБУ", price="Цена: 50000"):
    return (f"<h1>{title}</h1><table><tr><td>{native}</td></tr><tr><td>{buyer}</td></tr><tr><td>{price}</td></tr></table>").encode("utf-8")


def test_two_distinct_native_originals_only_from_current_listing():
    result = index_notices(official_synthetic_listing())
    assert len(result) == 2
    assert result[0][2] == "https://goszakaz.e-dag.ru/smallpurchases/GzwSP/Notice?noticeLink=10980001"
    for n, title, url in result:
        assert detail_proof(synthetic_detail(title), n, title, url) == (n, title, url)


@pytest.mark.parametrize("url", [
    "http://goszakaz.e-dag.ru/smallpurchases/GzwSP/Notice?noticeLink=10980001",
    "https://evil.example/smallpurchases/GzwSP/Notice?noticeLink=10980001",
    "https://goszakaz.e-dag.ru.evil.example/smallpurchases/GzwSP/Notice?noticeLink=10980001",
    "/smallpurchases/GzwSP/Notice?noticeLink=10980001&session=123",
    "/smallpurchases/GzwSP/Notice?noticeLink=10980001&noticeLink=10980002",
    "/smallpurchases/GzwSP/Notice?noticeLink=10980001#foo",
    "/smallpurchases/GzwSP/Notice?noticeLink=abc",
    "https://user:pass@goszakaz.e-dag.ru/smallpurchases/GzwSP/Notice?noticeLink=10980001",
    "//evil.example/smallpurchases/GzwSP/Notice?noticeLink=10980001",
])
def test_cross_host_auth_query_and_redirect_links_are_rejected(url):
    assert canonical(url) is None


def test_fake_login_and_missing_native_list_do_not_pass():
    with pytest.raises(ValueError):
        index_notices(b"<html><body>Login required</body></html>")
    with pytest.raises(ValueError):
        index_notices(b"<div>There are 21731 notices</div>")
    with pytest.raises(ValueError):
        index_notices(official_synthetic_listing().replace(b"10980002", b"10980001"))


def test_corrupt_original_detail_is_fail_closed():
    n, title, url = index_notices(official_synthetic_listing())[0]
    for doc in (
        synthetic_detail("Другая закупка"),
        synthetic_detail(title, native="NO ORIGINAL PROCUREMENT NUMBER"),
        synthetic_detail(title, buyer="Поставщик: ГБУ"),
        synthetic_detail(title, price="Без цены"),
        ("<script>ИМЗ-2026-123456 Заказчик: ГБУ Цена: 50000</script>").encode("utf-8"),
    ):
        with pytest.raises(ValueError):
            detail_proof(doc, n, title, url)


def test_host_is_exact_official_domain():
    assert HOST == "goszakaz.e-dag.ru"
    assert LIST == "https://goszakaz.e-dag.ru/smallpurchases/GzwSP/NoticesGrid"
