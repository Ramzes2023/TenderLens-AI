"""Real-only anonymous search: store-backed projection and server-side redaction."""
import json
import sqlite3

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.database.backend import Database
from app.database.config import DatabaseSettings


def _database(tmp_path):
    db = Database(DatabaseSettings("sqlite:///guest-search.sqlite", tmp_path / "guest-search.sqlite"))
    with db.connect() as conn:
        conn.execute(
            "CREATE TABLE source_opportunities ("
            "source_id TEXT NOT NULL, external_id TEXT NOT NULL, "
            "notice_json TEXT NOT NULL, connector_version TEXT NOT NULL, "
            "first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, "
            "PRIMARY KEY(source_id, external_id))"
        )
        conn.commit()
    return db


def _store(db, *, title, external_id="original-001", last_seen="2026-10-23T09:00:00Z",
           source="eis", summary="Поставка для нужд предприятия"):
    notice = {
        "source": source,
        "external_id": external_id,
        "title": title,
        "url": "https://example.invalid/private/original",
        "customer": "СЕКРЕТНЫЙ ЗАКАЗЧИК",
        "tender_number": "SECRET-TENDER-123",
        "region": "СЕКРЕТНЫЙ РЕГИОН",
        "summary": summary,
        "initial_price": 11700.0,
        "currency": "RUB",
        "deadline": "2026-10-28T10:00:00+03:00",
        "enrichment": {"hidden": "PRIVATE-CONTACT"},
    }
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO source_opportunities "
            "(source_id,external_id,notice_json,connector_version,first_seen,last_seen) "
            "VALUES (?,?,?,?,?,?)",
            (source, external_id, json.dumps(notice, ensure_ascii=False),
             "connector-sync-v1:eis:adapter-r1", last_seen, last_seen),
        )
        conn.commit()


def test_anonymous_search_uses_real_persisted_notices_and_never_returns_private_fields(tmp_path):
    db = _database(tmp_path)
    _store(db, title="Поставка медицинского оборудования")
    with TestClient(create_app(runtime=ApiRuntime(database=db))) as client:
        response = client.get("/api/v1/public/opportunities?q=МЕДИЦИНСКОГО")
        assert response.status_code == 200
        data = response.json()
        assert data["shown"] == 1
        assert data["source"] == "stored_connector_notices"
        assert data["results"] == [{
            "title": "Поставка медицинского оборудования",
            "initial_price": 11700.0,
            "currency": "RUB",
            "deadline": "2026-10-28T10:00:00+03:00",
        }]
        raw = response.text
        for forbidden in ("СЕКРЕТНЫЙ", "PRIVATE-CONTACT", "SECRET-TENDER",
                          "example.invalid", "external_id", "customer",
                          "notice_json", "connector_version", "source_id"):
            assert forbidden not in raw
        assert response.headers["cache-control"].startswith("no-store")
        assert response.headers["referrer-policy"] == "no-referrer"
    db.close()


def test_guest_empty_and_no_fake_cards_when_no_notices(tmp_path):
    db = _database(tmp_path)
    with TestClient(create_app(runtime=ApiRuntime(database=db))) as client:
        response = client.get("/api/v1/public/opportunities")
        assert response.status_code == 200
        assert response.json()["results"] == []
        assert response.json()["shown"] == 0
        _store(db, title="Строительство моста")
        # The next request must read fresh contents of the same persisted store.
        found = client.get("/api/v1/public/opportunities?q=МОСТА")
        assert found.json()["shown"] == 1
        assert found.json()["results"][0]["title"] == "Строительство моста"
        missing = client.get("/api/v1/public/opportunities?q=водолазные")
        assert missing.json()["results"] == []
        assert client.get("/api/v1/public/opportunities/original-001").status_code == 404
    db.close()


def test_no_shared_database_cannot_fall_back_to_demo_data():
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        response = client.get("/api/v1/public/opportunities?q=строительство")
        assert response.status_code == 503
        assert response.headers["cache-control"].startswith("no-store")


def test_guest_search_rate_limit_and_max_query_length(tmp_path):
    db = _database(tmp_path)
    with TestClient(create_app(runtime=ApiRuntime(database=db))) as client:
        assert client.get("/api/v1/public/opportunities?q=" + "x" * 121).status_code == 422
        for _ in range(24):
            assert client.get("/api/v1/public/opportunities?q=слово").status_code == 200
        blocked = client.get("/api/v1/public/opportunities?q=слово")
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1
    db.close()


def test_website_has_guest_form_and_no_results_seeded_into_markup():
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert 'id="guestSearchForm"' in page.text
        assert "/assets/guest_search.js" in page.text
        assert "/api/v1/public/opportunities" not in page.text  # API fetched client-side
        assert "15 459 закупок" not in page.text


def test_title_containing_url_is_redacted_before_api_response(tmp_path):
    db = _database(tmp_path)
    _store(db, title="Поставка краски https://secret.example/notice/abc",
           external_id="abc")
    with TestClient(create_app(runtime=ApiRuntime(database=db))) as client:
        result = client.get("/api/v1/public/opportunities?q=краски").json()
        assert result["shown"] == 1
        assert "secret.example" not in json.dumps(result, ensure_ascii=False)
    db.close()

def test_guest_search_does_not_allow_probing_redacted_url_words(tmp_path):
    db = _database(tmp_path)
    _store(db, title="Поставка химии https://classified.example/notice/verysecret",
           external_id="secured")
    with TestClient(create_app(runtime=ApiRuntime(database=db))) as client:
        assert client.get("/api/v1/public/opportunities?q=verysecret").json()["results"] == []
        assert client.get("/api/v1/public/opportunities?q=химии").json()["shown"] == 1
    db.close()


def test_guest_redacts_buyer_email_even_if_embedded_in_title(tmp_path):
    db = _database(tmp_path)
    _store(db, title="Закупка ПАО СЕКРЕТНАЯ КОМПАНИЯ team@private.example мебели",
           external_id="secured")
    with db.connect() as conn:
        notice = json.loads(conn.execute("SELECT notice_json FROM source_opportunities").fetchone()[0])
        notice["customer"] = "ПАО СЕКРЕТНАЯ КОМПАНИЯ"
        conn.execute("UPDATE source_opportunities SET notice_json=?", (json.dumps(notice, ensure_ascii=False),))
        conn.commit()
    with TestClient(create_app(runtime=ApiRuntime(database=db))) as client:
        data = client.get("/api/v1/public/opportunities?q=мебели").json()
        assert data["shown"] == 1
        payload = json.dumps(data, ensure_ascii=False)
        assert "СЕКРЕТНАЯ КОМПАНИЯ" not in payload
        assert "private.example" not in payload
        assert client.get("/api/v1/public/opportunities?q=СЕКРЕТНАЯ").json()["results"] == []
        assert client.get("/api/v1/public/opportunities?q=team").json()["results"] == []
    db.close()
