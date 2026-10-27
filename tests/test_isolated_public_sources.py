"""No-premature-cutover tests for the isolated procurement public-feed service."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.isolated_public_sources import create_public_source_app
from app.database.backend import Database
from app.database.config import DatabaseSettings
from scripts.verify_isolated_public_source_release import eligible_public_previews


def make_db(tmp_path):
    return Database(DatabaseSettings("",tmp_path/"source-only.sqlite"))


def add(db, *, external_id="84", title="Поставка электрического оборудования",
        now=None, deadline=None, last_seen=None, source="mikroton_tender"):
    now = now or datetime.now(timezone.utc)
    deadline = deadline or (now+timedelta(days=3))
    last_seen = last_seen or now
    notice = {
        "source": source,
        "external_id": external_id,
        "title": title,
        "url": (f"https://tender.mt52.ru/tenders/{external_id}" if source=="mikroton_tender"
                else "https://stantorgi.ru/etp/RJvFVqJX"),
        "customer": "SECRET BUYER INSIDE WORKER STORAGE",
        "summary": "INTERNAL DETAIL NOT GUEST",
        "initial_price": 77000.0,
        "currency": "RUB",
        "deadline": deadline.isoformat(),
    }
    with db.connect() as connection:
        connection.execute(
            "INSERT INTO source_opportunities "
            "(source_id,external_id,notice_json,connector_version,first_seen,last_seen) "
            "VALUES (?,?,?,?,?,?)",
            (source,external_id,json.dumps(notice),f"connector-sync-v1:{source}:adapter-r1",
             last_seen.isoformat(),last_seen.isoformat()),
        )
        connection.commit()


def test_isolated_public_service_exposes_only_safe_projection_and_public_aggregates(tmp_path):
    db=make_db(tmp_path)
    with TestClient(create_public_source_app(database_factory=lambda:db)) as client:
        assert client.get("/_internal/health").json()["database"]=="isolated"
        for forbidden in ("/", "/register", "/login", "/health",
                          "/api/v1/organizations/1/companies",
                          "/api/v1/public/help/ask", "/docs", "/openapi.json",
                          "/api/v1/public/opportunities/84"):
            assert client.get(forbidden).status_code==404
        assert client.get("/api/v1/public/opportunities?q=оборудования").json()["shown"]==0
        add(db, external_id="80", title="Поставка старого оборудования",
            deadline=datetime.now(timezone.utc)-timedelta(days=2))
        assert client.get("/api/v1/public/opportunities?q=старого").json()["shown"]==0
        add(db)
        reply=client.get("/api/v1/public/opportunities?q=оборудования")
        assert reply.status_code==200
        preview=reply.json()
        assert preview["shown"]==1
        assert set(preview["results"][0])=={"title","initial_price","currency","deadline"}
        assert "SECRET BUYER" not in reply.text
        assert "INTERNAL DETAIL" not in reply.text
        assert "tender.mt52.ru" not in reply.text
        assert "external_id" not in reply.text
        assert reply.headers["cache-control"].startswith("no-store")
        pulse=client.get("/api/v1/public/market-pulse")
        assert pulse.status_code==200
        assert pulse.json()["scope"]=="bounded_persisted_source_observations"
        intelligence=client.get("/api/v1/public/market-intelligence")
        assert intelligence.status_code==200
        assert intelligence.json()["scanned_recent_rows"]==2
        assert "SECRET BUYER" not in intelligence.text
    assert db._closed


def test_promotion_gate_rejects_archive_and_old_observations(tmp_path):
    now=datetime(2026,10,27,12,0,tzinfo=timezone.utc)
    db=make_db(tmp_path)
    with TestClient(create_public_source_app(database_factory=lambda:db)):
        assert eligible_public_previews(db,now=now)["promotion_ready"] is False
        add(db,external_id="1",now=now,deadline=now-timedelta(hours=1))
        assert eligible_public_previews(db,now=now)["promotion_ready"] is False
        add(db,external_id="2",now=now,deadline=now+timedelta(days=2),
            last_seen=now-timedelta(days=1))
        assert eligible_public_previews(db,now=now)["promotion_ready"] is False
        add(db,external_id="3",now=now,deadline=now+timedelta(days=2))
        gate=eligible_public_previews(db,now=now)
        assert gate["promotion_ready"] is True
        assert gate["fresh_open_originals"]==1
        add(db,external_id="ЗК-2026-000020",source="stan_commercial_public",
            title="Поставка пожарных шкафов",now=now,deadline=now+timedelta(days=1))
        gate=eligible_public_previews(db,now=now)
        assert gate["fresh_open_originals"]==2
        assert gate["by_source"]=={"mikroton_tender":1,"stan_commercial_public":1}



def test_isolated_service_requires_explicit_db_and_flag(monkeypatch):
    monkeypatch.delenv("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED",raising=False)
    monkeypatch.setenv("DATABASE_URL","sqlite:////app/data/tenderlens.db")
    with pytest.raises(RuntimeError,match="not explicitly enabled"):
        with TestClient(create_public_source_app()):
            pass
    monkeypatch.setenv("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED","true")
    with pytest.raises(RuntimeError,match="database location mismatch"):
        with TestClient(create_public_source_app()):
            pass


def test_source_compose_never_attaches_prod_db_or_publishes_public_port():
    raw=Path("ops/public_sources/compose.yaml").read_text(encoding="utf-8")
    assert "services:\n  guest-sources:" in raw
    assert "    ports:" not in raw
    assert "type=bind" not in raw
    assert "tenderlens-vps_tenderlens_data" not in raw
    assert "tenderlens_data" not in raw
    assert "sqlite:////app/data/isolated-public-sources.sqlite3" in raw
    assert 'MIKROTON_TENDER_ENABLED: "true"' in raw
    assert 'STAN_COMMERCIAL_PUBLIC_ENABLED: "true"' in raw
    assert "    api:" not in raw and "    caddy:" not in raw and "    bot:" not in raw
    assert "    network_mode: none" in raw
    assert "VALYQON_RU_BACKGROUND_CATALOG_ENABLED: \"false\"" in raw
    assert "    external: true" in raw
