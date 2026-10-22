"""Synthetic adversarial detail contracts. Never count fixtures as live source proof."""
import pytest

from scripts.research_ru_samara_native_details import verify_original_detail


def original(*, number="ИМЗ-2026-123456", title="Поставка мебели",
             buyer="Муниципальная школа Самары"):
    return (f'<html><body><main><h1>{title}</h1><p>Реестровый номер: {number}</p>'
            f'<p>Заказчик: {buyer}</p></main></body></html>').encode("utf-8")


def test_exact_native_number_title_and_buyer_required():
    assert verify_original_detail(original(),
           number="ИМЗ-2026-123456", title="Поставка мебели",
           buyer="Муниципальная школа Самары")


@pytest.mark.parametrize("kwargs", [
    {"number": "EIS-123"},
    {"number": "ИМЗ-2026-000000"},
    {"title": "Вымышленная поставка"},
    {"buyer": "Другой покупатель"},
])
def test_wrong_original_identity_or_metadata_rejected(kwargs):
    info={"number":"ИМЗ-2026-123456",
          "title":"Поставка мебели",
          "buyer":"Муниципальная школа Самары"}
    info.update(kwargs)
    with pytest.raises(ValueError):
        verify_original_detail(original(), **info)


def test_html_login_page_cannot_be_counted_as_original():
    body=b"<html><body>Login required</body></html>"
    with pytest.raises(ValueError):
        verify_original_detail(body, number="ИМЗ-2026-123456",
                               title="Поставка мебели",
                               buyer="Муниципальная школа Самары")


def test_even_full_metadata_in_document_still_rejects_login_gate():
    page=original().replace(b"</body>", "Необходима авторизация</body>".encode("utf-8"))
    with pytest.raises(ValueError, match="requires login"):
        verify_original_detail(page, number="ИМЗ-2026-123456",
                               title="Поставка мебели",
                               buyer="Муниципальная школа Самары")
