"""Synthetic offline tests; no source adapters or application runtime required."""
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

# Import this independent module without executing the source package's adapters.
MODULE_PATH = Path(__file__).resolve().parents[1] / "app/sources/ru_notice_changes.py"
SPEC = importlib.util.spec_from_file_location("ru_notice_changes", MODULE_PATH)
engine = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = engine
SPEC.loader.exec_module(engine)
Observation = engine.Observation
ObservationKey = engine.ObservationKey
compare = engine.compare_observations
NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
KEY = ObservationKey("eis:44-FZ", "0000123456789012345", "001")
VALUES = {
    "title": "Поставка оборудования", "buyer": "Заказчик", "buyer_inn": "0012345678",
    "price": Decimal("100.00"), "currency": "RUB", "deadline": NOW + timedelta(days=7),
    "status": "published", "okpd2_codes": ["26.20.11.110"],
    "ktru_codes": ["26.20.11.110-00000001"], "document_ids": ["doc-001", "doc-002"],
}


def obs(values=None, complete=None, at=NOW, key=KEY, **kwargs):
    return Observation(key, at, VALUES if values is None else values,
                       engine.FIELDS if complete is None else complete, **kwargs)


def pair(values, complete=None, **kwargs):
    return compare(obs(), obs(values, complete, NOW + timedelta(seconds=1), **kwargs))


def test_first_and_complete_unchanged():
    first = compare(None, obs())
    assert first.status == "first_observation"
    assert first.previous_fingerprint is None and first.changes == ()
    assert pair(dict(VALUES)).status == "unchanged"
    empty = compare(None, obs({}, ()))
    assert empty.status == "first_observation"
    assert empty.unobserved_fields == engine.FIELDS
    assert compare(obs({}, ()), obs({}, (), NOW + timedelta(seconds=1))).status == "insufficient_data"


@pytest.mark.parametrize("field,value", [
    ("price", Decimal("101")), ("deadline", NOW + timedelta(days=8)),
    ("status", "source_cancelled"), ("buyer", "Другой заказчик"),
    ("buyer_inn", "0012345679"), ("title", "Работы"), ("currency", "USD"),
    ("okpd2_codes", ["26.20.11.120"]), ("ktru_codes", ["26.20.11.110-00000002"]),
    ("document_ids", ["doc-002", "doc-003"]),
])
def test_supported_changes(field, value):
    result = pair({**VALUES, field: value})
    assert result.status == "changed"
    assert len(result.changes) == 1
    assert result.changes[0].field == field
    assert result.changes[0].change_type == "modified"


@pytest.mark.parametrize("complete", [(), engine.FIELDS])
def test_missing_never_removes_even_with_mask(complete):
    result = pair({"price": Decimal("100")}, complete)
    assert result.status == "insufficient_data" and not result.changes
    assert "document_ids" in result.unobserved_fields


def test_partial_can_establish_scalar_and_report_change():
    result = pair({"price": Decimal("102")}, ())
    assert result.status == "changed" and result.unobserved_fields
    assert result.changes[0].current_value == Decimal("102")
    assert compare(obs({"price": Decimal("102")}, ()), obs(at=NOW + timedelta(seconds=1))).status == "changed"


@pytest.mark.parametrize("field", engine.FIELDS)
def test_explicit_confirmed_removal(field):
    result = pair({**VALUES, field: None})
    assert result.status == "changed"
    assert result.changes[0].change_type == "removed"
    assert pair({**VALUES, field: None}, ()).status == "insufficient_data"


def test_addition_requires_known_absence():
    previous = obs({**VALUES, "title": None})
    assert compare(previous, obs(at=NOW + timedelta(seconds=1))).changes[0].change_type == "added"
    assert compare(obs({}, ()), obs(at=NOW + timedelta(seconds=1))).status == "insufficient_data"


def test_collections_order_duplicates_and_partial_evidence():
    result = pair({**VALUES, "document_ids": ["doc-002", "doc-001", "doc-001"]})
    assert result.status == "unchanged"
    assert result.previous_fingerprint == result.current_fingerprint
    partial = pair({**VALUES, "document_ids": ["doc-002"]}, ())
    assert not partial.changes and partial.status == "insufficient_data"
    partial = pair({**VALUES, "document_ids": ["doc-003"]}, ())
    assert partial.changes[0].current_value == ("doc-001", "doc-002", "doc-003")
    old = obs({**VALUES, "document_ids": ["doc-001"]}, ())
    new = obs({**VALUES, "document_ids": ["doc-002"]}, at=NOW + timedelta(seconds=1))
    result = compare(old, new)
    assert result.changes[0].current_value == ()  # confirmed removal only, no unproven addition
    assert result.changes[0].change_type == "modified"


def test_empty_document_list_requires_completeness():
    result = pair({**VALUES, "document_ids": []})
    assert result.changes[0].change_type == "removed"
    assert result.changes[0].current_value == ()
    result = pair({**VALUES, "document_ids": []}, ())
    assert result.status == "insufficient_data" and not result.changes


def test_unconfirmed_none_cannot_establish_addition():
    previous = obs({**VALUES, "buyer": None}, ())
    result = compare(previous, obs(at=NOW + timedelta(seconds=1)))
    assert result.status == "insufficient_data" and not result.changes
    assert "unconfirmed_absence" in {i.code for i in result.issues}


@pytest.mark.parametrize("key", [
    ObservationKey(KEY.namespace, KEY.procurement_id, "002"),
    ObservationKey(KEY.namespace, KEY.procurement_id),
    ObservationKey(KEY.namespace, "123456789012345"),
    ObservationKey("eis:223-FZ", KEY.procurement_id, "001"),
])
def test_identity_mismatch(key):
    result = pair(VALUES, key=key)
    assert result.status == "identity_mismatch" and not result.changes


def test_chronology_and_opaque_revisions():
    assert compare(obs(), obs(at=NOW - timedelta(seconds=1))).status == "out_of_order"
    assert compare(obs(), obs({**VALUES, "price": Decimal("2")})).status == "out_of_order"
    previous = obs(source_updated_at=NOW, source_revision="z")
    current = obs(at=NOW + timedelta(seconds=1), source_updated_at=NOW - timedelta(seconds=1))
    assert compare(previous, current).status == "out_of_order"
    current = obs(at=NOW + timedelta(seconds=1), source_revision="a")
    assert compare(previous, current).status == "unchanged"
    assert "revision_not_ordered" in {i.code for i in compare(previous, current).issues}


def test_equal_timezone_instants_and_precision():
    offset = timezone(timedelta(hours=3))
    result = pair({**VALUES, "deadline": VALUES["deadline"].astimezone(offset)})
    assert result.status == "unchanged" and result.previous_fingerprint == result.current_fingerprint
    assert compare(obs(), obs(at=NOW.astimezone(offset))).status == "unchanged"
    result = pair({**VALUES, "deadline": VALUES["deadline"].date()})
    assert result.status == "insufficient_data" and not result.changes
    assert "precision_mismatch" in {i.code for i in result.issues}
    assert compare(obs({**VALUES, "deadline": date(2026, 1, 1)}),
                   obs({**VALUES, "deadline": date(2026, 1, 2)}, at=NOW + timedelta(seconds=1))).status == "changed"


@pytest.mark.parametrize("value", [1.2, True, 1, "100", Decimal("NaN"), Decimal("sNaN"),
                                       Decimal("Infinity"), Decimal("-1"), Decimal("1e999999")])
def test_invalid_price(value):
    with pytest.raises(ValueError, match="price"):
        obs({"price": value})


@pytest.mark.parametrize("values", [
    {"deadline": datetime(2026, 1, 1)}, {"deadline": "2026-01-01"},
    {"buyer_inn": 1234567890}, {"buyer_inn": "123"}, {"currency": "rub"},
    {"title": ""}, {"title": " x "}, {"title": {}}, {"unknown": "x"},
    {"document_ids": "doc"}, {"document_ids": ["doc 1"]}, {"document_ids": [True]},
    {"okpd2_codes": ["garbage"]}, {"ktru_codes": ["26.20"]},
])
def test_malformed_fields(values):
    with pytest.raises(ValueError):
        obs(values)


@pytest.mark.parametrize("kwargs", [
    {"observed_at": datetime(2026, 1, 1)}, {"source_updated_at": date(2026, 1, 1)},
    {"source_revision": 2}, {"source_revision": ""}, {"complete_fields": ["title", "title"]},
    {"complete_fields": ["bogus"]}, {"complete_fields": "title"}, {"values": []}, {"key": "url"},
])
def test_malformed_observation(kwargs):
    with pytest.raises(ValueError):
        Observation(**{"key": KEY, "observed_at": NOW, "values": VALUES, **kwargs})


@pytest.mark.parametrize("identifier", [0, True, "", " 001", "001 002", "001\n", "я"])
def test_invalid_identity(identifier):
    with pytest.raises(ValueError):
        ObservationKey("eis", identifier)


def test_immutable_and_preserved_inputs():
    docs = ["doc-002", "doc-001", "doc-001"]
    values = {**VALUES, "document_ids": docs}
    mask = list(engine.FIELDS)
    original = obs(values, mask)
    compare(original, obs(at=NOW + timedelta(seconds=1)))
    assert values["document_ids"] is docs and len(docs) == 3
    docs.clear()
    values["price"] = Decimal("999")
    mask.clear()
    assert original.values["document_ids"] == ("doc-001", "doc-002")
    assert original.values["price"] == Decimal("100")
    with pytest.raises(TypeError):
        original.values["price"] = Decimal("1")
    with pytest.raises(FrozenInstanceError):
        original.key = KEY
    assert original.key.procurement_id.startswith("0000") and original.key.lot_id == "001"


def test_fingerprints_mask_metadata_decimal_context():
    full = compare(None, obs()).current_fingerprint
    assert full != compare(None, obs(complete=())).current_fingerprint
    assert full == compare(None, obs(source_revision="123", source_updated_at=NOW,
                                     at=NOW + timedelta(days=1))).current_fingerprint
    assert full == compare(None, obs(dict(reversed(list(VALUES.items()))))).current_fingerprint
    value = Decimal("123456789012345678901234567890.123456789")
    with localcontext() as ctx:
        ctx.prec = 2
        first = compare(None, obs({"price": value}, ())).current_fingerprint
    assert first == compare(None, obs({"price": value}, ())).current_fingerprint
    assert compare(None, obs({"price": Decimal("-0.00")}, ())).current_fingerprint == compare(None, obs({"price": Decimal("0")}, ())).current_fingerprint


def test_fingerprint_across_processes():
    code = (
        "import importlib.util,sys; from datetime import datetime,timezone; "
        f"s=importlib.util.spec_from_file_location('ru_notice_changes',{str(MODULE_PATH)!r}); "
        "m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m); "
        "o=m.Observation(m.ObservationKey('eis','001'),datetime(2026,1,1,tzinfo=timezone.utc),"
        "{'document_ids': {'b','a'}}, {'document_ids'});print(m.compare_observations(None,o).current_fingerprint)"
    )
    outputs = [subprocess.check_output([sys.executable, "-B", "-c", code], text=True).strip() for _ in range(3)]
    assert len(set(outputs)) == 1 and len(outputs[0]) == 64


def test_bounds():
    obs({"title": "x" * engine.MAX_STRING_CHARS}, ())
    with pytest.raises(ValueError):
        obs({"title": "x" * (engine.MAX_STRING_CHARS + 1)})
    with pytest.raises(ValueError):
        obs({"document_ids": ["a"] * (engine.MAX_COLLECTION_ITEMS + 1)})
    with pytest.raises(ValueError, match="budget"):
        obs({"document_ids": ["x" * 200] * 200})
    with pytest.raises(ValueError):
        ObservationKey("eis", "1" * (engine.MAX_IDENTIFIER_CHARS + 1))
    with pytest.raises(ValueError):
        obs({"price": Decimal("1" * (engine.MAX_DECIMAL_DIGITS + 1))})
    with pytest.raises(ValueError):
        obs({"document_ids": iter(["a"])})


@pytest.mark.parametrize("law", ["44-FZ", "223-FZ"])
def test_law_compatible_metadata(law):
    key = ObservationKey(f"eis:{law}", "000123", "01")
    result = compare(None, obs(key=key, source_revision="rev-0001", source_updated_at=NOW))
    assert result.key == key and result.schema_version == engine.SCHEMA_VERSION
    assert result.status == "first_observation"


def test_invalid_compare_arguments():
    with pytest.raises(ValueError):
        compare({}, obs())
    with pytest.raises(ValueError):
        compare(None, {})
