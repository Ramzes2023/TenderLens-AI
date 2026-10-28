"""Synthetic negative tests never count as live Dagestan public notice evidence."""
import pytest
from scripts.research_ru_dagestan_two_native_details import (
    DETAIL_IDS, canonical_detail, original_detail_evidence,
)


def example_detail(item_id="5611345", buyer=True, price=True, deadline=True):
    fields = [
        "<html><body><h1>Поставка оборудования для местной школы</h1>",
        f"<p>Реестровая запись {item_id}</p>",
        "<p>ИМЗ-2026-009912</p>",
    ]
    if buyer:
        fields.append("<p>Заказчик: Муниципальная школа</p>")
    if price:
        fields.append("<p>НМЦК: 320000 руб.</p>")
    if deadline:
        fields.append("<p>Окончание подачи заявок 25.10.2026</p>")
    fields.append("</body></html>")
    return "".join(fields).encode("utf-8")


def test_only_two_fixed_bounded_first_party_link_ids():
    assert DETAIL_IDS == ("5611345", "5611196")
    assert canonical_detail("5611345") == "https://goszakaz.e-dag.ru/smallpurchases/GzwSP/5611345"
    for bad in ("1", "abc", "123?a=b", "//evil.test", "9999999999999"):
        with pytest.raises(ValueError):
            canonical_detail(bad)


def test_full_original_detail_requires_identity_native_number_buyer_price_deadline():
    assert all(original_detail_evidence(example_detail(), "5611345"))
    with pytest.raises(ValueError):
        original_detail_evidence(example_detail(), "5611196")
    for body in (
        example_detail(buyer=False),
        example_detail(price=False),
        example_detail(deadline=False),
        b"<html><h1>Login</h1><p>Password</p></html>",
        b"<script>document.write('Fake buyer/price')</script>",
        b"x" * 200,
    ):
        with pytest.raises(ValueError):
            original_detail_evidence(body, "5611345")


def test_script_only_fake_original_details_dont_count():
    page = (
        b"<html><script>"
        + example_detail()
        + b"</script><h1>Portal authentication</h1></html>"
    )
    with pytest.raises(ValueError):
        original_detail_evidence(page, "5611345")
