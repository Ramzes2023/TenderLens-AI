"""Sixth official Samara source is strictly list-only and time-safe."""
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path

from app.api.guest_search_routes import search_persisted_notices
from app.api.public_source_deadline import eligible_published_deadline
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.sources.opportunities import OpportunityRepository
from app.sources.ru_samara_public_list import GRID,SOURCE_ID
from scripts.verify_samara_list_sixth_candidate import verify_samara_list_candidate

NOW=datetime(2026,10,28,16,0,tzinfo=timezone.utc)


def test_official_samara_public_list_date_and_clock_require_worldwide_future():
    verify=lambda value:eligible_published_deadline(SOURCE_ID,value,now=NOW)
    # It is already 06:00 on 29 Oct in UTC+14. 29 Oct 15:05 still qualifies.
    assert verify("29.10.2026 15:05")
    assert verify("29.10.2026 15:05:00")
    assert verify("2026-10-29T15:05:00")
    assert not verify("29.10.2026 06:00")
    assert not verify("29.10.2026 05:59:59")
    assert not verify("29.10.2026")
    assert verify("30.10.2026")
    assert not verify("28.10.2026 23:59")
    assert not verify("31.02.2027 15:05")
    assert not verify("29.10.2026 26:30")
    assert not verify("2026-10-29T15:05:00+04:00")
    assert not verify("2026-10-29T15:05:00Z")
    assert not verify("2026-10-29T15:05")
    assert not verify("29.10.2026 15:05 extra")
    assert not eligible_published_deadline("not_samara","29.10.2026 15:05",now=NOW)


def db_for(tmp_path):
    db=Database(DatabaseSettings("",tmp_path/"isolated.sqlite"))
    OpportunityRepository(db).initialize()
    return db


def put(db,*,id="5611345",number="ИМЗ-2026-100001",deadline="29.10.2026 15:05",
        observed=NOW,original=GRID,region="Самарская область",buyer="Самарская больница",
        price=15000,currency="RUB"):
    notice={"source":SOURCE_ID,"external_id":id,"tender_number":number,
            "title":"Поставка холодильного оборудования для больницы",
            "url":original,"published_at":"27.10.2026",
            "deadline":deadline,"customer":buyer,"region":region,
            "initial_price":price,"currency":currency,
            "summary":"PRIVATE CUSTOMER CONTACT AND INTERNAL RECORD",
            }
    with db.connect() as c:
        c.execute(
            "INSERT INTO source_opportunities "
            "(source_id,external_id,notice_json,connector_version,first_seen,last_seen) "
            "VALUES (?,?,?,?,?,?)",
            (SOURCE_ID,id,json.dumps(notice,ensure_ascii=False),
             "connector-sync-v1:"+SOURCE_ID+":adapter-r1",
             observed.isoformat(),observed.isoformat()),
        )
        c.commit()


def test_real_list_only_guest_preview_carries_no_protected_details(tmp_path):
    db=db_for(tmp_path)
    assert not verify_samara_list_candidate(db,now=NOW)["candidate_ready"]
    put(db)
    evidence=verify_samara_list_candidate(db,now=NOW)
    assert evidence["safely_open_public_list_rows"]==1
    assert evidence["verified_individual_details"] is False
    out=search_persisted_notices(db,"холодильного",active_only=True,now=NOW)
    assert out["shown"]==1
    item=out["results"][0]
    assert set(item)=={"title","initial_price","currency","deadline"}
    assert item["deadline"]=="29.10.2026 15:05"
    assert item["initial_price"]==15000 and item["currency"]=="RUB"
    assert "PRIVATE" not in json.dumps(item)
    assert "5611345" not in json.dumps(item)
    assert "webtorgi" not in json.dumps(item)
    assert "Самарская больница" not in json.dumps(item)
    db.close()


def test_invalid_list_identity_stale_closed_missing_buyer_never_promoted(tmp_path):
    db=db_for(tmp_path)
    put(db,id="5611346",deadline="29.10.2026 01:00")
    put(db,id="5611347",deadline="30.10.2026",observed=NOW-timedelta(hours=3))
    put(db,id="5611348",deadline="30.10.2026",original="https://fake.invalid/private")
    put(db,id="5611349",deadline="30.10.2026",region="Другое место")
    put(db,id="5611350",deadline="30.10.2026",buyer="")
    put(db,id="5611351",deadline="30.10.2026",price=None,currency="RUB")
    put(db,id="5611352",deadline="30.10.2026",number="FAKE")
    assert verify_samara_list_candidate(db,now=NOW)["safely_open_public_list_rows"]==0
    assert search_persisted_notices(db,"холодильного",active_only=True,now=NOW)["shown"]==0
    db.close()


def test_samara_is_optin_on_top_of_existing_five_and_not_prod():
    base=Path("ops/public_sources/compose.yaml").read_text(encoding="utf8")
    south=Path("ops/public_sources/compose.south-ural.yaml").read_text(encoding="utf8")
    caucasus=Path("ops/public_sources/compose.kavkaz-rf.yaml").read_text(encoding="utf8")
    lenobl=Path("ops/public_sources/compose.lenobl.yaml").read_text(encoding="utf8")
    sixth=Path("ops/public_sources/compose.samara-list.yaml").read_text(encoding="utf8")
    assert 'RU_SAMARA_PUBLIC_LIST_ENABLED: "false"' in base
    assert 'SOUTH_URAL_PUBLIC_ENABLED: "true"' in south
    assert 'KAVKAZ_RF_FIRSTPARTY_ENABLED: "true"' in caucasus
    assert 'LENOBL_SMALL_PUBLIC_ENABLED: "true"' in lenobl
    assert sixth.count('RU_SAMARA_PUBLIC_LIST_ENABLED: "true"')==4
    assert 'VALYQON_CONNECTOR_MAX_RECORDS: "30"' in sixth
    assert "ports:" not in sixth and "volumes:" not in sixth
    assert "tenderlens-vps" not in sixth.split("services:",1)[1]
