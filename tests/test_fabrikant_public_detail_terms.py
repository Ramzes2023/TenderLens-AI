"""Fabrikant original deadline: real Moscow-labelled time, not inferred UTC."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.sources.fabrikant_public_detail_terms import original_terms
from app.sources.ru_chechnya_fabrikant44 import (
    HOST, INN, ORGANIZER, SOURCE_ID, verified_fabrikant_notice,
)

NUMBER="0194200000526005756"
TITLE="Услуги по организации и проведению праздничных мероприятий"
URL=f"https://{HOST}/44/procedure/ea21/{NUMBER}"


def page(*, value="05.11.2026 •09:00 (МСК+00:00)", price="222 240.00",
         extra="", currency="Российский рубль"):
    return (
        f"<html><h1>Сведения о закупке {NUMBER}</h1>"
        f"<div>Общие сведения о закупке</div>"
        f"<p>Наименование закупки {TITLE}</p>"
        f"<div>Валюта {currency}</div>"
        f"<p>Начальная (максимальная) цена {price}</p>"
        f"<section>Сведения об организаторе закупки "
        f"{ORGANIZER} ИНН {INN}</section>"
        f"<div>Сроки проведения закупки и подачи заявок</div>"
        f"<p>Дата и время публикации извещения 27.10.2026 •11:00 (МСК+00:00)</p>"
        f"<p>Дата и время окончания срока подачи заявок {value}</p>"
        f"{extra}</html>"
    ).encode("utf8")


def test_preserves_true_moscow_offset_and_numeric_original_amount():
    terms=original_terms(page())
    assert terms=={
        "deadline":"2026-11-05T09:00:00+03:00",
        "initial_price":222240.0,
        "currency":"RUB",
    }
    assert datetime.fromisoformat(terms["deadline"]).astimezone(timezone.utc)==(
        datetime(2026,11,5,6,0,tzinfo=timezone.utc)
    )
    notice=verified_fabrikant_notice(page(),number=NUMBER,url=URL,title=TITLE)
    assert notice.source==SOURCE_ID
    assert notice.deadline==terms["deadline"]
    assert notice.initial_price==222240.0
    assert notice.currency=="RUB"
    assert notice.customer==ORGANIZER


def test_msk_plus_zero_is_not_utc_plus_zero():
    value="06.11.2026 14:15 (MSK+00:00)"
    assert original_terms(page(value=value))["deadline"]=="2026-11-06T14:15:00+03:00"


def test_no_timezone_or_unsupported_timezone_cannot_be_guessed():
    for value in ("05.11.2026 09:00",
                  "05.11.2026 09:00 (МСК+01:00)",
                  "05.11.2026 09:00 (UTC+00:00)",
                  "05.11.2026 09:00 (GMT+00:00)"):
        assert original_terms(page(value=value))["deadline"] is None


def test_hidden_embedded_and_unrelated_deadlines_cannot_override():
    hidden=(
        "<script>Дата и время окончания срока подачи заявок "
        "31.12.2099 23:59 (МСК+00:00)</script>"
        "<template>Дата и время окончания срока подачи заявок "
        "31.12.2099 23:59 (МСК+00:00)</template>"
    )
    assert original_terms(page(extra=hidden))["deadline"]=="2026-11-05T09:00:00+03:00"
    assert original_terms(page(
        value="05.11.2026 09:00 (МСК+00:00)",
        extra="<p>Дата и время проведения процедуры подачи ценовых предложений "
              "20.11.2026 09:00 (МСК+00:00)</p>"
    ))["deadline"]=="2026-11-05T09:00:00+03:00"


def test_conflicting_or_malformed_visible_deadlines_fail_closed():
    other="<p>Дата и время окончания срока подачи заявок 07.11.2026 11:00 (МСК+00:00)</p>"
    assert original_terms(page(extra=other))["deadline"] is None
    with pytest.raises(ValueError):
        original_terms(page(value="31.02.2026 09:00 (МСК+00:00)"))


def test_prices_are_missing_without_proven_rubles_and_conflicts_not_assumed():
    assert original_terms(page(currency="Доллар США"))["initial_price"] is None
    assert original_terms(page(extra="<p>Начальная (максимальная) цена 900 000.00</p>")
                          )["initial_price"] is None
    assert original_terms(page(price="Цена не установлена"))["currency"] is None
    assert original_terms(page(price="99999999999999999999999999999999"))["currency"] is None


def test_no_labeled_submission_field_does_not_invent_a_deadline():
    raw=(f"<html><h1>{TITLE}</h1>"
         "Прием заявок 2026-11-05 дата подведения итогов 2026-11-06</html>").encode()
    assert original_terms(raw)=={
        "deadline":None,"initial_price":None,"currency":None,
    }
