"""Strict offline contracts. Synthetic test HTML is never accepted as live proof."""
from dataclasses import replace
from pathlib import Path

import pytest

from app.sources.models import TenderNotice
from app.sources.stan_commercial_public import (
    independently_verified_commercial_metadata, verify_detail, LIST_URL
)

NUMBER = "ЗК-2026-000020"
TITLE = "Поставка пожарных шкафов"
URL = LIST_URL + "/RScxkWBC"


def detail(*fields):
    return (
        "<h1>" + TITLE + "</h1>"
        "<div>Коммерческая закупка</div><div>Номер процедуры</div><div>" + NUMBER + "</div>"
        + "".join("<div>" + key + "</div><div>" + value + "</div>" for key, value in fields)
    ).encode("utf-8")


def test_first_party_original_fields_are_verified_and_typed():
    data = detail(
        ("Наименование заказчика", "АО Завод металлургических изделий"),
        ("Дата и время окончания подачи заявок", "22.10.2026 12:30 (МСК)"),
        ("Начальная цена", "1 235 000,50 ₽"),
    )
    assert verify_detail(data, NUMBER, TITLE, URL) == (NUMBER, TITLE, URL)
    assert independently_verified_commercial_metadata(data, NUMBER, TITLE, URL) == {
        "customer": "АО Завод металлургических изделий",
        "deadline": "2026-10-22T12:30:00+03:00",
        "initial_price": 1235000.5,
        "currency": "RUB",
    }


def test_missing_optional_original_fields_remain_unknown():
    evidence = independently_verified_commercial_metadata(detail(), NUMBER, TITLE, URL)
    assert evidence == {"customer": None, "deadline": None, "initial_price": None, "currency": None}


def test_explicit_unknown_price_cannot_be_fabricated():
    evidence = independently_verified_commercial_metadata(
        detail(("Начальная цена", "Не указана")), NUMBER, TITLE, URL,
    )
    assert evidence["initial_price"] is None and evidence["currency"] is None


@pytest.mark.parametrize("mutated", [
    detail(("Наименование заказчика", "ГБУ Покупатель"),
           ("Наименование заказчика", "ООО Другой заказчик")),
    detail(("Дата и время окончания подачи заявок", "22.10.2026 12:30")),
    detail(("Дата и время окончания подачи заявок", "31.02.2026 12:30 (МСК)")),
    detail(("Дата и время окончания подачи заявок", "22.10.2026 27:30 (МСК)")),
    detail(("Начальная цена", "100,00 USD")),
    detail(("Начальная цена", "NaN ₽")),
    detail(("Начальная цена", "9999999999999,00 ₽")),
    detail(("Наименование заказчика", "<script>Подмена</script>")),
])
def test_invalid_or_conflicting_detail_metadata_fails_closed(mutated):
    with pytest.raises(ValueError):
        independently_verified_commercial_metadata(mutated, NUMBER, TITLE, URL)


def test_unverified_detail_never_exposes_metadata():
    for number, title, url in [
        ("ЗК-2026-000021", TITLE, URL),
        (NUMBER, "Несоответствующий предмет", URL),
        (NUMBER, TITLE, "https://evil.example/etp/RScxkWBC"),
    ]:
        with pytest.raises(ValueError):
            independently_verified_commercial_metadata(
                detail(("Наименование заказчика", "АО Реальный покупатель")), number, title, url,
            )


def test_script_content_is_not_firstparty_metadata():
    payload = detail() + "<script>Наименование заказчика ООО Подмена</script>".encode("utf-8")
    assert independently_verified_commercial_metadata(payload, NUMBER, TITLE, URL)["customer"] is None


def test_storage_and_local_keyword_search_roundtrip(tmp_path):
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    from app.sources.ingestion import connector_version
    from app.sources.opportunities import OpportunityRepository

    db = Database(DatabaseSettings("stan-metadata-offline", tmp_path / "metadata.sqlite"))
    try:
        store = OpportunityRepository(db)
        store.initialize()
        details = independently_verified_commercial_metadata(
            detail(("Наименование заказчика", "АО Завод металлургических изделий"),
                   ("Дата и время окончания подачи заявок", "22.10.2026 12:30 (МСК)"),
                   ("Начальная цена", "1 235 000,50 ₽")), NUMBER, TITLE, URL,
        )
        notice = TenderNotice(source="stan_commercial_public", external_id=NUMBER,
                              tender_number=NUMBER, title=TITLE, url=URL, **details)
        assert store.upsert(notice, connector_version("stan_commercial_public"))
        matches = store.read("stan_commercial_public", search_terms=("металлургических",))
        assert len(matches) == 1
        assert matches[0].customer == notice.customer
        assert matches[0].deadline == notice.deadline
        assert matches[0].initial_price == notice.initial_price
        assert matches[0].currency == "RUB"
        assert not store.upsert(notice, connector_version("stan_commercial_public"))
        assert len(store.read("stan_commercial_public", search_terms=(NUMBER,))) == 1
    finally:
        db.close()
