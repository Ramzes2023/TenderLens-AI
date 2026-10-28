"""South Ural third-source opt-in must not alter the current public two-source deployment."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.sources.opportunities import OpportunityRepository
from scripts.verify_south_ural_public_site_candidate import canonical_original, verify


NOW = datetime(2026, 10, 28, 9, 30, tzinfo=timezone.utc)


def _db(tmp_path):
    db = Database(DatabaseSettings("", tmp_path / "separate.sqlite"))
    OpportunityRepository(db).initialize()
    return db


def _add(db, *, identity="109877", deadline=None, observed=None, url=None,
         region="Челябинская область"):
    deadline = deadline or NOW + timedelta(days=2)
    observed = observed or NOW
    url = url or f"https://www.vendorportal.ru/Market/OfferInvitationOpen/View/{identity}?isReadOnly=True"
    notice = {"source":"south_ural_public", "external_id":identity,
              "title":"Поставка оборудования для школы",
              "url":url, "region":region, "deadline":deadline.isoformat(),
              "customer":"ПОЛНОЕ НАЗВАНИЕ ЗАКАЗЧИКА", "summary":"PROTECTED_DETAIL",
              "initial_price":None, "currency":None}
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO source_opportunities "
            "(source_id,external_id,notice_json,connector_version,first_seen,last_seen)"
            " VALUES(?,?,?,?,?,?)",
            ("south_ural_public", identity, json.dumps(notice,ensure_ascii=False),
             "connector-sync-v1:south_ural_public:adapter-r1", observed.isoformat(),
             observed.isoformat()),
        )
        conn.commit()


def test_canonical_official_url_accepts_only_exact_readonly_no_leaks():
    good="https://www.vendorportal.ru/Market/OfferInvitationOpen/View/109877?isReadOnly=True"
    assert canonical_original("109877",good)
    for bad in (good.replace("www.vendorportal.ru","attacker.example"),
                good.replace("isReadOnly=True","isReadOnly=False"),
                good+"&token=secret",good+"#fragment",good.replace("109877","109878"),
                good.replace("https://","http://"),"https://www.vendorportal.ru.evil.test/View/109877"):
        assert not canonical_original("109877",bad)


def test_fresh_only_requires_true_origins_and_future_submission_window(tmp_path):
    db=_db(tmp_path)
    assert verify(db,now=NOW)["candidate_ready"] is False
    _add(db,identity="109877")
    assert verify(db,now=NOW)["verified_recent_open_originals"]==1
    _add(db,identity="109878", deadline=NOW-timedelta(minutes=1))
    _add(db,identity="109879", observed=NOW-timedelta(hours=3))
    _add(db,identity="109880", url="https://attacker.example/Market/OfferInvitationOpen/View/109880?isReadOnly=True")
    _add(db,identity="109881", region="Другой регион")
    result=verify(db,now=NOW)
    assert result["verified_recent_open_originals"]==1
    assert result["candidate_ready"]
    db.close()


def test_third_source_is_overlay_only():
    base=Path("ops/public_sources/compose.yaml").read_text(encoding="utf-8")
    overlay=Path("ops/public_sources/compose.south-ural.yaml").read_text(encoding="utf-8")
    assert 'SOUTH_URAL_PUBLIC_ENABLED: "false"' in base
    assert overlay.count('SOUTH_URAL_PUBLIC_ENABLED: "true"')==4
    assert "public_source_data" not in overlay
    assert "tenderlens-vps" not in overlay.split("services:", 1)[1]
    assert "ports:" not in overlay
    assert "volumes:" not in overlay
