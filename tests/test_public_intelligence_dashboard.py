"""Dense marketing visualizations must contain only actual bounded connector data."""
import json
from datetime import date
from fastapi.testclient import TestClient
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.public_intelligence_routes import market_intelligence_snapshot
from app.database.backend import Database
from app.database.config import DatabaseSettings


def _db(tmp_path):
    db = Database(DatabaseSettings("sqlite:///market-intelligence.sqlite", tmp_path / "market-intelligence.sqlite"))
    with db.connect() as conn:
        conn.execute(
            "CREATE TABLE source_opportunities (source_id TEXT, external_id TEXT, "
            "notice_json TEXT NOT NULL, connector_version TEXT NOT NULL, "
            "first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, "
            "PRIMARY KEY(source_id, external_id))"
        )
        conn.commit()
    return db


def _save(db, key, first, **notice_fields):
    notice = {
        "title": "Real procurement " + key,
        "source": "SENSITIVE_PLATFORM",
        "external_id": key,
        "url": "https://secret.example/tender/" + key,
        "customer": "SECRET BUYER",
        "summary": "SECRET BUYER CONTACT",
        **notice_fields
    }
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO source_opportunities "
            "(source_id,external_id,notice_json,connector_version,first_seen,last_seen)"
            " VALUES (?,?,?,?,?,?)",
            ("SENSITIVE_PLATFORM", key, json.dumps(notice), "v1", first, first),
        )
        conn.commit()


def test_real_observations_create_all_distributions_and_no_secret_leak(tmp_path):
    db = _db(tmp_path)
    _save(db, "a", "2026-10-23T09:00:00Z",
          initial_price=650_000, currency="RUB", deadline="2026-10-26")
    _save(db, "b", "2026-10-20T09:00:00Z",
          initial_price=4_500_000, currency="RUB", deadline="2026-12-04")
    _save(db, "c", "2026-10-09T09:00:00Z",
          initial_price=650, currency="USD", deadline="2026-10-16")
    _save(db, "d", "2026-10-17T09:00:00Z",
          initial_price=0, currency="RUB", deadline="bad-date")
    _save(db, "e", "2026-10-20T09:00:00Z", currency="EUR")
    data = market_intelligence_snapshot(db, today=date(2026,10,23))
    assert data["scanned_recent_rows"] == 5
    assert data["valid_records_in_sample"] == 5
    assert data["new_notices_14d"] == 4
    assert data["week_comparison"] == {"previous_7d": 1, "latest_7d": 3}
    assert len(data["daily"]) == 14
    assert data["daily"][-1] == {"date":"2026-10-23","count":1,"priced":1}
    assert data["priced_notices"] == 4
    assert data["priced_rub_notices"] == 3
    assert data["rub_price_bands"]["under_1m"] == 2
    assert data["rub_price_bands"]["1_to_5m"] == 1
    assert data["currency_counts"]["RUB"] == 3
    assert data["currency_counts"]["USD"] == 1
    assert data["currency_counts"]["EUR"] == 1
    assert data["deadline_bands"]["within_7d"] == 1
    assert data["deadline_bands"]["over_30d"] == 1
    assert data["deadline_bands"]["overdue"] == 1
    assert data["deadline_bands"]["unspecified"] == 2
    assert data["field_coverage"] == {"title":5,"price":4,"currency":5,"deadline":3}
    raw = json.dumps(data)
    for hidden in ("SENSITIVE", "secret.example", "SECRET BUYER", "customer",
                   "source_id", "notice_json", "external_id", "https://"):
        assert hidden not in raw
    db.close()


def test_missing_data_must_not_be_replaced_with_showcase_figures(tmp_path):
    db = _db(tmp_path)
    with TestClient(create_app(runtime=ApiRuntime(database=db))) as client:
        result = client.get("/api/v1/public/market-intelligence")
        assert result.status_code == 200
        payload = result.json()
        assert payload["valid_records_in_sample"] == 0
        assert payload["new_notices_14d"] == 0
        assert sum(payload["currency_counts"].values()) == 0
        assert result.headers["cache-control"].startswith("no-store")
    db.close()


def test_storage_unavailable_fails_closed():
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        result = client.get("/api/v1/public/market-intelligence")
        assert result.status_code == 503
        assert "no-store" in result.headers["cache-control"]


def test_premium_dashboard_exposes_real_chart_mounts_and_no_static_market_claims():
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        response = client.get("/")
        assert response.status_code == 200
        html = response.text
    for marker in ("id=\"vqxHeroLine\"", "id=\"vqxDailyChart\"", "id=\"vqxPriceDonut\"",
                   "id=\"vqxDeadlineBars\"", "id=\"vqxCurrencyBars\"",
                   "id=\"vqxPriceHistogram\"", "id=\"vqxCoverageBars\"",
                   "id=\"vqxWeeksBars\"", "id=\"guestSearchForm\"",
                   "/assets/public_intelligence.js", "/assets/public_luxe.css"):
        assert marker in html
    for invented in ("15 459", "360 млн", "15M+", "50+", "98% reliable",
                     "14 days of full access", "440+"):
        assert invented not in html
    assert "No search has been run here" in html
