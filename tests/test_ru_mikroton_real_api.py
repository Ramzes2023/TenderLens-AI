"""Offline security and identity tests for unmocked Russian API acceptance."""
import json
import pytest
from scripts.ci_ru_mikroton_real_api import public_records


def envelope(items):
    return json.dumps({"meta": {"api_version": "v1"}, "items": items}).encode()


def tender(identity=42, title="Настоящая закупка"):
    return {"id": identity, "title": title,
            "portal_url": f"https://tender.mt52.ru/tenders/{identity}"}


def test_documented_public_api_schema_identity():
    records, count = public_records(envelope([tender()]))
    assert count == 1
    assert records[0]["id"] == 42
    assert public_records(envelope([]))[1] == 0


@pytest.mark.parametrize("value", [
    {"id": 1, "title": "abc", "portal_url": "http://tender.mt52.ru/tenders/1"},
    {"id": 1, "title": "abc", "portal_url": "https://tender.mt52.ru.evil.invalid/tenders/1"},
    {"id": 1, "title": "abc", "portal_url": "https://user@tender.mt52.ru/tenders/1"},
    {"id": 1, "title": "abc", "portal_url": "https://tender.mt52.ru/tenders/1?token=s"},
    {"id": 1, "title": "abc", "portal_url": "https://tender.mt52.ru/tenders/2"},
    {"id": 1, "title": "abc", "portal_url": "https://tender.mt52.ru/tenders/1#x"},
    {"id": True, "title": "abc", "portal_url": "https://tender.mt52.ru/tenders/True"},
    {"id": 1, "title": " ", "portal_url": "https://tender.mt52.ru/tenders/1"},
])
def test_wrong_identity_or_url_fails_closed(value):
    with pytest.raises(ValueError):
        public_records(envelope([value]))


def test_oversized_or_unexpected_document_rejected():
    with pytest.raises(ValueError):
        public_records(b"x" * 1_048_577)
    with pytest.raises(ValueError):
        public_records(json.dumps({"items": [tender()]}).encode())
    with pytest.raises(ValueError):
        public_records(json.dumps({"meta": {"api_version": "v2"}, "items": []}).encode())
    with pytest.raises((ValueError, TypeError)):
        public_records(b"not-json")
