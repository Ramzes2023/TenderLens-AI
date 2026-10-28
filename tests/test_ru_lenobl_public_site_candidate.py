"""Fifth source is an opt-in and cannot show expired or fabricated deadlines."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.api.guest_search_routes import search_persisted_notices
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.sources.opportunities import OpportunityRepository
from scripts.verify_lenobl_public_site_candidate import verify_lenobl_candidate

NOW=datetime(2026,10,28,12,0,tzinfo=timezone.utc)
SOURCE="lenobl_small_public"
HOST="zakupki.lenreg.ru"


def database(tmp_path):
    db=Database(DatabaseSettings("",tmp_path/"isolated.sqlite"))
    OpportunityRepository(db).initialize()
    return db


def insert(db, *, ident="35217482", deadline="2026-10-29T14:30:00",observed=NOW,
           url=None,source=SOURCE,price=None):
    url=url or f"https://{HOST}/ProductRequestGroup/Index/{ident}"
    notice={"source":source,"external_id":ident,
            "title":"Поставка компьютерной техники и расходных материалов",
            "url":url,"deadline":deadline,"initial_price":price,
            "currency":None, "tender_number":None,
            "summary":"PRIVATE INTERNAL BUYER TERMS"}
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO source_opportunities "
            "(source_id,external_id,notice_json,connector_version,first_seen,last_seen) "
            "VALUES(?,?,?,?,?,?)",
            (source,ident,json.dumps(notice,ensure_ascii=False),
             "connector-sync-v1:"+source+":adapter-r1",observed.isoformat(),
             observed.isoformat()),
        )
        conn.commit()


def test_live_active_preview_and_strict_candidate_share_deadline_rule(tmp_path):
    db=database(tmp_path)
    assert not verify_lenobl_candidate(db,now=NOW)["candidate_ready"]
    insert(db)
    assert verify_lenobl_candidate(db,now=NOW)["recent_open_official_rows"]==1
    resp=search_persisted_notices(db,"компьютерной",active_only=True,now=NOW)
    assert resp["shown"]==1
    result=resp["results"][0]
    assert set(result)=={"title","initial_price","currency","deadline"}
    assert result["deadline"]=="2026-10-29T14:30:00"
    assert result["initial_price"] is None
    assert result["currency"] is None
    assert "PRIVATE" not in json.dumps(result)
    db.close()


def test_original_host_expiry_no_time_no_leak_gate(tmp_path):
    db=database(tmp_path)
    insert(db,ident="35217481",deadline="2026-10-29T01:00:00")
    insert(db,ident="35217480",deadline="2026-11-01T11:00:00",observed=NOW-timedelta(hours=3))
    insert(db,ident="35217479",deadline="2026-11-01T11:00:00",
           url="https://evil.invalid/ProductRequestGroup/Index/35217479")
    insert(db,ident="35217478",deadline="2026-11-01T11:00:00",price=1234)
    insert(db,ident="35217477",deadline="2026-11-01T12:00:00+03:00")
    assert verify_lenobl_candidate(db,now=NOW)["recent_open_official_rows"]==0
    assert search_persisted_notices(db,"компьютерной",active_only=True,now=NOW)["shown"]==0
    db.close()


def test_fifth_source_does_not_modify_live_four_source_stack():
    base=Path("ops/public_sources/compose.yaml").read_text(encoding="utf8")
    kav=Path("ops/public_sources/compose.kavkaz-rf.yaml").read_text(encoding="utf8")
    fifth=Path("ops/public_sources/compose.lenobl.yaml").read_text(encoding="utf8")
    assert 'LENOBL_SMALL_PUBLIC_ENABLED: "false"' in base
    assert 'KAVKAZ_RF_FIRSTPARTY_ENABLED: "true"' in kav
    assert fifth.count('LENOBL_SMALL_PUBLIC_ENABLED: "true"')==4
    assert "ports:" not in fifth and "volumes:" not in fifth
    assert "tenderlens-vps" not in fifth.split("services:",1)[1]


def test_untzoned_local_clock_exact_global_boundary_without_time_guess():
    from app.api.public_source_deadline import eligible_published_deadline
    verify=lambda dt: eligible_published_deadline(SOURCE, dt, now=NOW)
    # At noon UTC on 28 October it is already 02:00 on 29 October in UTC+14.
    assert verify("2026-10-29T02:00:01")
    assert not verify("2026-10-29T02:00:00")
    assert not verify("2026-10-29T01:59:59")
    assert verify("2026-10-29T14:30:00")
    assert not verify("2026-10-29")
    assert verify("2026-10-29T14:30")
    assert not verify("2026-10-29T14:30:00Z")  # official portal does not supply a timezone
    assert not eligible_published_deadline("other_source","2026-10-29T14:30:00",now=NOW)
