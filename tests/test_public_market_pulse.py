"""Public market charts must be real DB aggregates without private data."""
import json
from datetime import date

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.public_market_routes import market_pulse_snapshot
from app.database.backend import Database
from app.database.config import DatabaseSettings


def database(tmp_path):
    db = Database(DatabaseSettings("sqlite:///pulse.sqlite", tmp_path / "pulse.sqlite"))
    with db.connect() as conn:
        conn.execute(
            "CREATE TABLE source_opportunities ("
            "source_id TEXT NOT NULL, external_id TEXT NOT NULL, "
            "notice_json TEXT NOT NULL, connector_version TEXT NOT NULL, "
            "first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, "
            "PRIMARY KEY(source_id,external_id))"
        )
        conn.commit()
    return db


def insert(db, *, key, first_seen, last_seen=None):
    payload = json.dumps({
        "source": "commercial_secret_key", "external_id": key,
        "title": "Real tender " + key, "url": "https://private-origin.invalid/" + key,
        "customer": "SENSITIVE CUSTOMER"
    })
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO source_opportunities "
            "(source_id,external_id,notice_json,connector_version,first_seen,last_seen)"
            " VALUES (?,?,?,?,?,?)",
            ("commercial_secret_key", key, payload, "connector-r1",
             first_seen, last_seen or first_seen),
        )
        conn.commit()


def test_market_pulse_aggregates_saved_data_not_private_records(tmp_path):
    db = database(tmp_path)
    insert(db, key="one", first_seen="2026-10-23T09:00:00+00:00")
    insert(db, key="two", first_seen="2026-10-23T11:00:00+00:00")
    insert(db, key="three", first_seen="2026-10-20T21:20:00Z")
    insert(db, key="older", first_seen="2026-08-01T00:00:00Z",
           last_seen="2026-10-23T12:00:00Z")
    data = market_pulse_snapshot(db, today=date(2026, 10, 23))
    assert data["new_notices_in_sample"] == 3
    assert data["scanned_recent_rows"] == 4
    assert len(data["days"]) == 14
    assert data["days"][-1] == {"date": "2026-10-23", "count": 2}
    assert next(item["count"] for item in data["days"] if item["date"] == "2026-10-20") == 1
    raw = json.dumps(data)
    for hidden in ("customer", "source_id", "secret", "private-origin",
                   "notice_json", "external_id", "https://", "commercial"):
        assert hidden not in raw
    db.close()


def test_public_market_endpoint_empty_is_zero_not_fiction(tmp_path):
    db = database(tmp_path)
    with TestClient(create_app(runtime=ApiRuntime(database=db))) as client:
        result = client.get("/api/v1/public/market-pulse")
        assert result.status_code == 200
        assert result.json()["new_notices_in_sample"] == 0
        assert result.json()["scanned_recent_rows"] == 0
        assert result.json()["scope"] == "bounded_persisted_source_observations"
        assert result.headers["cache-control"].startswith("no-store")
    db.close()


def test_market_endpoint_fails_closed_without_real_storage():
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        response = client.get("/api/v1/public/market-pulse")
        assert response.status_code == 503
        assert response.headers["referrer-policy"] == "no-referrer"


def test_guest_search_cannot_probe_private_summary_or_buyer(tmp_path):
    db = database(tmp_path)
    with db.connect() as conn:
        record = {
            "source": "private_platform", "external_id": "private-number",
            "title": "Поставка оборудования",
            "customer": "СЕКРЕТНАЯ КОМПАНИЯ", "summary": "уникальный_секретный_токен"
        }
        conn.execute(
            "INSERT INTO source_opportunities "
            "(source_id,external_id,notice_json,connector_version,first_seen,last_seen) "
            "VALUES (?,?,?,?,?,?)",
            ("private_platform", "private-number", json.dumps(record,ensure_ascii=False),
             "adapter-r1", "2026-10-23", "2026-10-23"),
        )
        conn.commit()
    with TestClient(create_app(runtime=ApiRuntime(database=db))) as client:
        for q in ("уникальный_секретный_токен", "СЕКРЕТНАЯ", "private_platform",
                  "private-number"):
            result = client.get("/api/v1/public/opportunities", params={"q": q})
            assert result.status_code == 200
            assert result.json()["results"] == []
        found = client.get("/api/v1/public/opportunities?q=оборудования")
        assert found.json()["shown"] == 1
        assert found.json()["results"][0]["title"] == "Поставка оборудования"
    db.close()


def test_showcase_is_real_and_honest_public_markup():
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        html = client.get("/").text
    for item in ("vqStageTitle", "vqPulseChart", "vqPulseStatus", "vqHelpDrawer",
                 "vqOpenHelp", "vqFloatingHelp", "guestSearchForm",
                 "/assets/public_showcase.css", "/assets/public_showcase.js"):
        assert item in html
    assert "No search has been run here" in html
    assert "INTERACTIVE DEMO" in html
    assert "15 459" not in html
    assert "440+" not in html
