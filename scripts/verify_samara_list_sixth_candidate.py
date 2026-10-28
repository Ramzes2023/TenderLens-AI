"""Strict stored official Samara LIST-ONLY candidate gate.

Checks independently public-grid-owned native number, identity, title,
buyer, source-published deadline and fresh SQL observation. Deep-detail
cards were NOT accessible and are never asserted to be verified.
SQL candidate is insufficient for release: real official JSON -> leased
Worker -> SQLite -> HTTPS must independently corroborate it.
"""
from __future__ import annotations

import json
import os
from contextlib import closing
from datetime import datetime, timezone
import re

from app.api.guest_search_routes import _public_preview
from app.api.isolated_public_sources import ISOLATED_SQLITE_URL
from app.api.public_source_deadline import eligible_published_deadline
from app.sources.ru_samara_public_list import GRID, NATIVE_NUMBER, SOURCE_ID


def verify_samara_list_candidate(db, *, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("UTC-aware verification clock required")
    now = now.astimezone(timezone.utc)
    with closing(db.connect()) as conn:
        rows = conn.execute(
            "SELECT source_id,external_id,notice_json,last_seen "
            "FROM source_opportunities WHERE source_id=? "
            "ORDER BY last_seen DESC LIMIT 40", (SOURCE_ID,),
        ).fetchall()
    unique=set()
    for row in rows:
        try:
            observed=datetime.fromisoformat(str(row["last_seen"]).replace("Z","+00:00"))
            if observed.tzinfo is None:
                continue
            age=(now-observed.astimezone(timezone.utc)).total_seconds()
            if not 0 <= age <= 7200:
                continue
            notice=json.loads(row["notice_json"])
            if not isinstance(notice,dict):
                continue
            identity=row["external_id"]
            number=notice.get("tender_number")
            price=notice.get("initial_price")
            currency=notice.get("currency")
            if (type(identity) is not str
                or re.fullmatch(r"[0-9]{6,12}",identity) is None
                or notice.get("external_id")!=identity
                or notice.get("source")!=SOURCE_ID
                or type(number) is not str
                or NATIVE_NUMBER.fullmatch(number) is None
                or notice.get("url")!=GRID
                or notice.get("region")!="Самарская область"
                or type(notice.get("customer")) is not str
                or not notice["customer"].strip()
                or type(notice.get("title")) is not str
                or len(notice["title"].strip())<5
                or (price is None and currency is not None)
                or (price is not None and (
                    type(price) not in (int,float)
                    or not 0 < price <= 1e18 or currency!="RUB"))):
                continue
            if not eligible_published_deadline(
                SOURCE_ID,notice.get("deadline"),now=now):
                continue
            if _public_preview(notice) is None:
                continue
            unique.add((identity,number))
        except (ValueError,TypeError,OverflowError,AttributeError):
            continue
    return {"source":SOURCE_ID,"inspected":len(rows),"safely_open_public_list_rows":len(unique),
            "candidate_ready":bool(unique),"verified_individual_details":False}


def main() -> int:
    required={
        "VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED":"true",
        "DATABASE_URL":ISOLATED_SQLITE_URL,
        "RU_SAMARA_PUBLIC_LIST_ENABLED":"true",
        "LENOBL_SMALL_PUBLIC_ENABLED":"true",
        "KAVKAZ_RF_FIRSTPARTY_ENABLED":"true",
        "SOUTH_URAL_PUBLIC_ENABLED":"true",
    }
    if any(os.environ.get(k)!=v for k,v in required.items()):
        print("SAMARA_LIST_PUBLIC_PROMOTION=BLOCKED_CONFIG")
        return 2
    from app.database.backend import Database
    from app.database.config import load_database_settings
    db=Database(load_database_settings())
    try:
        result=verify_samara_list_candidate(db)
    except (OSError,ValueError):
        print("SAMARA_LIST_PUBLIC_PROMOTION=BLOCKED_STORE")
        return 2
    finally:
        db.close()
    print("SAMARA_SAFE_FUTURE_LIST_ROWS="+str(result["safely_open_public_list_rows"]))
    print("SAMARA_LIST_PUBLIC_PROMOTION="+(
        "CANDIDATE_ONLY" if result["candidate_ready"] else "BLOCKED_NO_FUTURE_LIST_ROW"))
    print("INDIVIDUAL_DEEP_DETAIL_VERIFIED=NO")
    print("LIVE_FIRSTPARTY_WORKER_AND_PUBLIC_HTTPS=REQUIRES_INDEPENDENT_PROOF")
    print("PRODUCTION_CHANGED=NO")
    return 0 if result["candidate_ready"] else 2


if __name__=="__main__":
    raise SystemExit(main())
