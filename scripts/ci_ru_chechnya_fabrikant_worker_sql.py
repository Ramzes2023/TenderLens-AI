"""Strict live Chechnya committee first-party originals -> fenced Worker -> SQL search.

No synthetic source rows, no proxy/auth/CAPTCHA bypass, no durable production
writes and no Telegram send. Fabricant 44-FZ is an EIS mirror, never an
independent unique publisher count.
"""
from __future__ import annotations
import asyncio
import json
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import connector_version
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from app.sources.ru_chechnya_fabrikant44 import HOST, ORGANIZER, REGION, SOURCE_ID
from scripts.ci_ru_leased_connector import run_leased_connector


def acceptance():
    catalog = build_source_catalog(MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=3,
        max_notifications_per_cycle=3, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        ru_chechnya_fabrikant44_enabled=True,
    ))
    if SOURCE_ID not in catalog.enabled_keys:
        raise AssertionError("Chechnya first-party operator opt-in missing")
    with tempfile.TemporaryDirectory(prefix="valyqon-chechnya-live-original-") as folder:
        db = Database(DatabaseSettings("ru-chechnya-live-worker",
                                       Path(folder) / "ephemeral.sqlite"))
        try:
            store = OpportunityRepository(db)
            store.initialize()
            stats = run_leased_connector(db, catalog, store, SOURCE_ID, max_records=3)
            count = stats["fetched_count"]
            if (not 2 <= count <= 3
                    or stats["accepted_count"] != count
                    or stats["inserted_count"] != count
                    or stats["skipped_count"] != 0
                    or stats["updated_count"] != 0):
                raise AssertionError("Genuine Chechnya source Worker SQL contract failed")
            rows = store.read(SOURCE_ID, limit=3)
            if len(rows) != count:
                raise AssertionError("Chechnya SQL row count disagrees with Worker")
            snapshot = snapshot_catalog(catalog, store)
            for notice in rows:
                target = urlsplit(notice.url)
                if (notice.source != SOURCE_ID
                        or notice.tender_number != notice.external_id
                        or not re.fullmatch(r"[0-9]{19}", notice.external_id)
                        or target.scheme != "https" or target.netloc != HOST
                        or not target.path.endswith("/" + notice.external_id)
                        or notice.region != REGION or notice.customer != ORGANIZER):
                    raise AssertionError("Unverified Chechnya region/ID original")
                found = asyncio.run(snapshot.fetch(
                    source_keys=(SOURCE_ID,), search_terms=(notice.external_id,),
                    limit_per_source=3,
                ))
                if found.failures or not any(
                    hit.identity == notice.identity and hit.url == notice.url
                    for hit in found.notices
                ):
                    raise AssertionError("Authentic Chechnya notice not locally searchable")
                if store.upsert(notice, connector_version(SOURCE_ID)):
                    raise AssertionError("Chechnya identical notice replay made a duplicate")
            return {"verified_regional_originals": count, "worker_sql_inserted": count,
                    "local_customer_query_matches": count, "idempotent": True,
                    "production_changed": False, "telegram_bot_api_receipt": False}
        finally:
            db.close()


def main():
    try:
        result = acceptance()
    except Exception as error:
        print("RU_CHECHNYA_FABRIKANT_WORKER_SQL=BLOCKED")
        print("FAILURE_CLASS=" + type(error).__name__)
        print("ACTUAL_TELEGRAM_MESSAGE_DELIVERED=NO")
        print("PRODUCTION_CHANGED=NO")
        return 1
    print("RU_CHECHNYA_FABRIKANT_EVIDENCE=" + json.dumps(result, sort_keys=True))
    print("RU_CHECHNYA_FABRIKANT_WORKER_SQL=PASS")
    print("ACTUAL_TELEGRAM_MESSAGE_DELIVERED=NO")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
