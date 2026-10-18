"""Prove real South Ural first-party buyer, deadline and price in ephemeral SQL."""
from __future__ import annotations
import asyncio
import json
import tempfile
from pathlib import Path

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.sources.south_ural_public import SouthUralPublicSource
from app.sources.opportunities import OpportunityRepository
from app.sources.ingestion import connector_version

SOURCE="south_ural_public"

def acceptance():
    notices=asyncio.run(SouthUralPublicSource(timeout=25).fetch(limit=2))
    if len(notices)!=2:
        raise AssertionError("Real two-notice South Ural metadata unavailable")
    if len({n.external_id for n in notices})!=2:
        raise AssertionError("Duplicate real notice identities")
    for notice in notices:
        if not notice.customer or not notice.deadline:
            raise AssertionError("Official customer or bid deadline not verified")
        if notice.currency not in (None,"RUB"):
            raise AssertionError("Unsupported currency")
    with tempfile.TemporaryDirectory(prefix="valyqon-ru-verified-metadata-") as tmp:
        db=Database(DatabaseSettings("ru-verified-metadata",Path(tmp)/"proof.sqlite"))
        try:
            store=OpportunityRepository(db)
            store.initialize()
            for notice in notices:
                if not store.upsert(notice, connector_version(SOURCE)):
                    raise AssertionError("Not newly saved in ephemeral database")
            stored=store.read(SOURCE,limit=2)
            if len(stored)!=2:
                raise AssertionError("Missing original first-party SQL results")
            for notice in notices:
                row=next((s for s in stored if s.identity==notice.identity),None)
                if (row is None or row.customer!=notice.customer
                    or row.deadline!=notice.deadline
                    or row.initial_price!=notice.initial_price
                    or row.currency!=notice.currency):
                    raise AssertionError("Source metadata did not survive SQL persistence")
        finally:
            db.close()
    return {
        "real_verified_origins":2,
        "buyer_fields":2,
        "deadline_fields":2,
        "price_fields":sum(n.initial_price is not None for n in notices),
        "sql_fields_roundtripped":2,
        "production_changed":False,
    }

if __name__=="__main__":
    try:
        result=acceptance()
    except Exception as e:
        print("RU_SOUTH_URAL_METADATA_LIVE=BLOCKED_"+type(e).__name__)
        print("PRODUCTION_CHANGED=NO")
        raise SystemExit(1)
    print("RU_SOUTH_URAL_METADATA_EVIDENCE="+json.dumps(result,sort_keys=True))
    print("RU_SOUTH_URAL_METADATA_LIVE=PASS")
    print("PRODUCTION_CHANGED=NO")
