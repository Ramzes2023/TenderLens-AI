"""Kavkaz.RF date-only public display is deliberately conservative."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.api.guest_search_routes import search_persisted_notices
from app.api.public_source_deadline import eligible_published_deadline
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.sources.opportunities import OpportunityRepository
from scripts.verify_kavkaz_public_site_candidate import verify_kavkaz_candidate

# At noon UTC, UTC+14 is already 29 October: a 29 October
# date-only deadline is ambiguous, so it MUST be rejected.
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
SOURCE = "kavkaz_rf_firstparty"
NUMBER = "ЗКЭФ-ДЭУК-1519"
ORIGINAL = (
    "https://xn--80aafvlc.xn--p1ai/"
    "purchases_sales/zakupki/tekushchie-/sample-procurement/detail-1519/"
)


def test_date_only_admits_only_provably_future_calendar_day():
    assert eligible_published_deadline(SOURCE, "2026-10-30", now=NOW)
    assert not eligible_published_deadline(SOURCE, "2026-10-29", now=NOW)
    assert not eligible_published_deadline(SOURCE, "2026-10-28", now=NOW)
    assert not eligible_published_deadline(SOURCE, "2026-10-27", now=NOW)
    assert not eligible_published_deadline("lenobl_small_public", "2026-11-09", now=NOW)
    assert not eligible_published_deadline(SOURCE, "2026-11-09 15:00", now=NOW)
    assert not eligible_published_deadline(SOURCE, "2026-13-03", now=NOW)
    assert not eligible_published_deadline(SOURCE, "2026-11-09T12:00:00", now=NOW)
    assert eligible_published_deadline(SOURCE, "2026-11-09T12:00:00+03:00", now=NOW)
    assert not eligible_published_deadline(SOURCE, "2026-10-28T09:00:00Z", now=NOW)


def test_future_date_only_preserved_not_fabricated_into_clock_time():
    from app.api.guest_search_routes import _public_preview
    n={"title":"Право заключения договора на поставку оборудования",
       "deadline":"2026-11-09", "initial_price":1000, "currency":"RUB"}
    assert _public_preview(n)["deadline"]=="2026-11-09"


def db_for(tmp_path):
    db=Database(DatabaseSettings("", tmp_path/"isolated.sqlite"))
    OpportunityRepository(db).initialize()
    return db


def save(db, *, identity=NUMBER, deadline="2026-10-30",
         observed=NOW, url=ORIGINAL, region="Северный Кавказ",
         source=SOURCE):
    notice={
        "source":source,"external_id":identity,"tender_number":identity,
        "title":"Право заключения договора на поставку спецодежды для горнолыжного комплекса",
        "url":url,"published_at":"2026-10-22","deadline":deadline,
        "customer":"АО «КАВКАЗ.РФ»", "initial_price":423093.0,
        "currency":"RUB","region":region,
        "summary":"PRIVATE PROCUREMENT TERMS NOT FOR GUEST",
    }
    with db.connect() as c:
        c.execute(
            "INSERT INTO source_opportunities "
            "(source_id,external_id,notice_json,connector_version,first_seen,last_seen) "
            "VALUES (?,?,?,?,?,?)",
            (source,identity,json.dumps(notice,ensure_ascii=False),
             f"connector-sync-v1:{source}:adapter-r1",
             observed.isoformat(),observed.isoformat())
        )
        c.commit()


def test_candidate_gate_and_actual_isolated_search_share_date_only_decision(tmp_path):
    db=db_for(tmp_path)
    assert not verify_kavkaz_candidate(db,now=NOW)["candidate_ready"]
    save(db)
    readiness=verify_kavkaz_candidate(db,now=NOW)
    assert readiness["candidate_ready"]
    assert readiness["fresh_canonical_open_originals"]==1
    assert readiness["independent_eis_dedup_proved"] is False
    guest=search_persisted_notices(db,"спецодежды",active_only=True,now=NOW)
    assert guest["shown"]==1
    item=guest["results"][0]
    assert set(item)=={"title","initial_price","currency","deadline"}
    assert item["deadline"]=="2026-10-30"
    assert "PRIVATE" not in json.dumps(item)
    assert "КАВКАЗ" not in json.dumps(item)
    assert "xn--" not in json.dumps(item)
    db.close()


def test_candidate_rejects_stale_archive_and_wrong_original(tmp_path):
    db=db_for(tmp_path)
    save(db, identity="ЗКЭФ-ДЭУК-1519", deadline="2026-10-29")  # too close
    save(db, identity="ЗКЭФ-ДЭУК-1520", deadline="2026-11-09",
         observed=NOW-timedelta(hours=3))
    save(db, identity="ЗКЭФ-ДЭУК-1521", deadline="2026-11-09",
         url="https://evil.invalid/purchases_sales/zakupki/tekushchie-/sample-procurement/detail-1521/")
    save(db, identity="ЗКЭФ-ДЭУК-1522", deadline="2026-11-09",
         region="Другой регион")
    assert verify_kavkaz_candidate(db,now=NOW)["fresh_canonical_open_originals"]==0
    db.close()


def test_opt_in_overlay_does_not_modify_existing_three_source_base():
    base=Path("ops/public_sources/compose.yaml").read_text(encoding="utf-8")
    south=Path("ops/public_sources/compose.south-ural.yaml").read_text(encoding="utf-8")
    kav=Path("ops/public_sources/compose.kavkaz-rf.yaml").read_text(encoding="utf-8")
    assert 'KAVKAZ_RF_FIRSTPARTY_ENABLED: "false"' in base
    assert 'SOUTH_URAL_PUBLIC_ENABLED: "true"' in south
    assert kav.count('KAVKAZ_RF_FIRSTPARTY_ENABLED: "true"')==4
    assert "volumes:" not in kav and "ports:" not in kav
    assert "tenderlens-vps" not in kav.split("services:",1)[1]
