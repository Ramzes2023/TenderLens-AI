"""Synthetic offline coverage for explicit Russian procurement metadata."""
import pytest

from app.sources.ru_procurement_signals import (
    MAX_FIELD_CHARS,
    extract_ru_procurement_signals as extract,
)


@pytest.mark.parametrize("text,law", [
    ("44-ФЗ", "44-FZ"), ("223-FZ", "223-FZ"),
    ("44 фз", "44-FZ"), ("223fz", "223-FZ"),
    ("44‑ФЗ", "44-FZ"), ("223 — fz", "223-FZ"),
    ("Федеральный закон № 44-ФЗ", "44-FZ"),
    ("Федерального закона №223", "223-FZ"),
    ("Federal Law No. 44-FZ", "44-FZ"),
    ("Federal Law 223", "223-FZ"),
    ("44-ФЗ / 223-ФЗ", "ambiguous"), ("Закупка", "unknown"),
])
def test_laws(text, law):
    assert extract({"description": text}).law == law


@pytest.mark.parametrize("text", [
    "44 223", "№ 44; № 223", "тендер 144-ФЗ", "x44-FZ",
    "44-FZserial", "serial-44-FZ", "serial‑44-ФЗ", "44-ФЗ‑123",
    "44-ФЗ_abc", "223-ФЗ.123",
    "ОКПД2 12.34.56.7890", "ОКПД2 12.34.56.789-12345678",
    "xОКПД2 12.34.56.789", "ОКПД20 12.34.56.789",
    "КТРУ 12.34.56.789-123456789", "КТРУ 12.34.56.789",
    "серийный номер 12.34.56.789", "ОКПД2 12.3", "ОКПД2 12.34.567",
    "ОКПД2 １２.３４", "ОКПД2 12.34.56.789abc",
])
def test_false_positives(text):
    result = extract({"description": text})
    assert result.law == "unknown"
    assert result.signals == ()


@pytest.mark.parametrize("code", ["12", "12.34", "12.34.5", "12.34.56", "12.34.56.789"])
def test_okpd_hierarchy(code):
    assert extract({"description": f"ОКПД 2: {code}"}).okpd2_codes == (code,)


def test_codes_unicode_and_spans():
    text = "🛒 е\u0308ж\u00a0OKPD2: 12.34.56.789; КТРУ № 12.34.56.789‑00000001; 44–ФЗ"
    result = extract({"description": text})
    assert result.okpd2_codes == ("12.34.56.789",)
    assert result.ktru_codes == ("12.34.56.789-00000001",)
    assert result.law == "44-FZ"
    assert len(result.signals) == 3
    for signal in result.signals:
        assert text[signal.start:signal.end] == signal.evidence
        assert signal.source_field == "description"
    assert result.signals[0].evidence == "OKPD2: 12.34.56.789"
    assert result.signals[1].evidence == "КТРУ № 12.34.56.789‑00000001"


def test_duplicate_conflict_and_deterministic_order():
    fields = {"summary": "223-ФЗ", "description": "44-ФЗ 44-ФЗ ОКПД2 12.34 ОКПД2 12.34",
              "title": "ОКПД2 99.99"}
    result = extract(fields)
    assert result == extract(dict(reversed(list(fields.items()))))
    assert result.law == "ambiguous"
    assert result.okpd2_codes == ("12.34", "99.99")
    assert len(result.signals) == 6
    assert result.signals[0].source_field == "title"
    assert result.signals[1].start == 0
    assert result.signals[2].start == 6


def test_non_content_metadata_is_ignored():
    assert extract({key: "44-ФЗ ОКПД2 12.34" for key in (
        "url", "buyer", "customer", "source", "platform", "tender_number",
        "external_id", "unexpected",
    )}).signals == ()


@pytest.mark.parametrize("fields", [None, {}, {"description": None}, {"description": ""}])
def test_missing(fields):
    result = extract(fields)
    assert result.law == "unknown"
    assert result.signals == result.issues == ()


@pytest.mark.parametrize("bad", [44, False, [], {}, b"44-FZ"])
def test_invalid_field(bad):
    result = extract({"description": bad, "title": "223-ФЗ"})
    assert result.law == "223-FZ"
    assert result.issues[0].reason == "invalid_type"
    assert result.issues[0].source_field == "description"


@pytest.mark.parametrize("bad", [44, False, [], "44-FZ"])
def test_invalid_container(bad):
    with pytest.raises(TypeError):
        extract(bad)


def test_bounds_skip_entire_field_and_continue():
    exact = "44-ФЗ" + " " * (MAX_FIELD_CHARS - 5)
    assert extract({"description": exact}).law == "44-FZ"
    result = extract({"description": exact + " ", "summary": "223-ФЗ"})
    assert result.law == "223-FZ"
    assert result.issues[0].reason == "too_long"
    assert extract({"description": "я" * MAX_FIELD_CHARS}).signals == ()


def test_labelled_latin_codes_and_no_unlabelled_continuation():
    result = extract({"classification_text": "KTRU code: 12.34.56.789-00000000; OKPD2 code: 12.34, 99.99"})
    assert result.ktru_codes == ("12.34.56.789-00000000",)
    assert result.okpd2_codes == ("12.34",)


def test_ktru_duplicates_distinct_values_and_control_characters():
    text = ("\x00КТРУ: 12.34.56.789-00000001; "
            "КТРУ: 12.34.56.789-00000001; КТРУ: 12.34.56.789-00000002")
    result = extract({"description": text})
    assert result.ktru_codes == ("12.34.56.789-00000001", "12.34.56.789-00000002")
    assert len(result.signals) == 3
    assert result.signals[0].start == 1


def test_labels_do_not_bridge_lines_or_excessive_separator_whitespace():
    result = extract({"description": "ОКПД2\n12.34; КТРУ" + " " * 40 + "12.34.56.789-00000000"})
    assert result.signals == ()
