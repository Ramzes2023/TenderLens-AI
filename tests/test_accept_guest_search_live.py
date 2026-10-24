"""Operator release smoke is read-only, strict and does not fabricate records."""
import json

import pytest

from scripts import accept_guest_search_live as smoke


def _response(items, *, market_rows=1):
    return [
        (200, {"Cache-Control": "no-store"}, b'<html>guestSearchForm vqPulseChart</html>'),
        (200, {"Cache-Control": "no-store"}, json.dumps({
            "source": "stored_connector_notices", "details_locked": True,
            "results": items
        }).encode()),
        (200, {"Cache-Control": "no-store"}, json.dumps({
            "scope": "bounded_persisted_source_observations",
            "days": [{"date": f"2026-10-{i+1:02d}", "count": 0} for i in range(14)],
            "new_notices_in_sample": market_rows,
        }).encode()),
    ]


def test_acceptance_requires_actual_stored_notices(monkeypatch):
    data = iter(_response([]))
    monkeypatch.setattr(smoke, "_get", lambda base, path: next(data))
    with pytest.raises(AssertionError, match="NO_PERSISTED_TENDERS"):
        smoke.verify("http://127.0.0.1:8000")


def test_acceptance_accepts_real_only_redacted_contract(monkeypatch):
    data = iter(_response([{
        "title": "Закупка ноутбуков", "initial_price": 5000, "currency": "RUB",
        "deadline": "2026-11-03T00:00:00Z"
    }]))
    monkeypatch.setattr(smoke, "_get", lambda base, path: next(data))
    result = smoke.verify("http://127.0.0.1:8000")
    assert result["stored_notice_previews"] == 1
    assert result["scope"] == "HTTP_PUBLIC_PROJECTION_ONLY"


@pytest.mark.parametrize("forbidden", ["url", "source", "customer", "external_id", "documents"])
def test_acceptance_fails_leaky_response(monkeypatch, forbidden):
    item = {"title": "Tender", "initial_price": None, "currency": None,
            "deadline": None, forbidden: "protected"}
    data = iter(_response([item]))
    monkeypatch.setattr(smoke, "_get", lambda base, path: next(data))
    with pytest.raises(AssertionError, match="unexpected fields"):
        smoke.verify("https://example.org")


def test_acceptance_does_not_send_to_remote_http(monkeypatch):
    called = []
    monkeypatch.setattr(smoke, "_get", lambda *args: called.append(args))
    with pytest.raises(ValueError, match="HTTPS"):
        smoke.verify("http://example.org")
    assert called == []


def test_acceptance_fails_contact_or_link_in_headline(monkeypatch):
    data = iter(_response([{"title": "Tender https://secret.invalid", "initial_price": 0,
                            "currency": "RUB", "deadline": None}]))
    monkeypatch.setattr(smoke, "_get", lambda base, path: next(data))
    with pytest.raises(AssertionError, match="prohibited link"):
        smoke.verify("http://localhost:8000")
