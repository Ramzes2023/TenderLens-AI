"""Strict real Chechnya Fabrikant 44-FZ -> actual durable connector handler -> ephemeral SQLite/search.

No mocked source records, account credentials, production database, redirects,
TLS bypass or LLM service. Nonempty real public data is mandatory.
"""
import asyncio
import json
import tempfile
from pathlib import Path

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import connector_version
from app.sources.ru_chechnya_fabrikant44 import canonical_detail, INN, ORGANIZER
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from scripts.ci_ru_leased_connector import run_leased_connector

SOURCE = "ru_chechnya_fabrikant44"


def acceptance():
    settings = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=3,
        max_notifications_per_cycle=5, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        ru_chechnya_fabrikant44_enabled=True,
    )
    catalog = build_source_catalog(settings)
    if SOURCE not in catalog.enabled_keys:
        raise AssertionError("Chechnya Fabrikant 44-FZ was not explicitly enabled")
    with tempfile.TemporaryDirectory(prefix="valyqon-ru-chechnya-worker-") as directory:
        db = Database(DatabaseSettings("ru-chechnya-live-worker", Path(directory) / "notices.sqlite"))
        try:
            store = OpportunityRepository(db)
            store.initialize()
            report = run_leased_connector(db, catalog, store, SOURCE, max_records=3)
            if (not 1 <= report["fetched_count"] <= 3
                    or report["accepted_count"] != report["fetched_count"]
                    or report["inserted_count"] != report["fetched_count"]
                    or report["skipped_count"] != 0
                    or report["updated_count"] != 0):
                raise AssertionError("No complete real worker ingestion")
            notices = store.read(SOURCE, limit=3)
            if len(notices) != report["fetched_count"]:
                raise AssertionError("Real worker database count mismatch")
            matches = 0
            snapshot = snapshot_catalog(catalog, store)
            for row in notices:
                if (row.source != SOURCE
                        or canonical_detail(row.url) != (row.external_id, row.url)
                        or row.customer != ORGANIZER
                        or row.tender_number != row.external_id):
                    raise AssertionError("Bad canonical source URL")
                found = asyncio.run(snapshot.fetch(
                    source_keys=(SOURCE,),
                    search_terms=(row.external_id,), limit_per_source=10,
                ))
                # Keyword search is substring-based, not an exact-ID filter:
                # short numeric IDs can occur in dates/prices of other notices.
                # Require the exact notice identity AND URL among results.
                if (found.failures or not any(
                        hit.identity == row.identity and hit.url == row.url
                        for hit in found.notices
                )):
                    raise AssertionError("Real worker keyword-search mismatch")
                # Replaying identical normalized notices changes no identities.
                if store.upsert(row, connector_version(SOURCE)):
                    raise AssertionError("Real worker identity was duplicated")
                matches += 1
            return {"real_independently_verified_original_details": report["fetched_count"],
                    "real_worker_inserted": report["inserted_count"],
                    "db_search_identities": matches,
                    "duplicate_replay_inserted": 0,
                    "eis_independent_feed": False,
                    "real_telegram_ack": False,
                    "production_changed": False}
        finally:
            db.close()


def main():
    try:
        evidence = acceptance()
    except Exception as error:
        print("RU_CHECHNYA_FABRIKANT_LIVE_WORKER=BLOCKED")
        print("FAILURE_CLASS=" + type(error).__name__)
        # Only allowlisted non-sensitive worker stages. No raw remote exception.
        if type(error) is AssertionError:
            static = {
                "Chechnya Fabrikant 44-FZ was not explicitly enabled": "CATALOG_OPT_IN",
                "No complete real worker ingestion": "WORKER_COUNTS",
                "Real worker database count mismatch": "SQL_COUNT",
                "Bad canonical source URL": "ORIGINAL_IDENTITY",
                "Real worker keyword-search mismatch": "SAVED_SEARCH",
                "Real worker identity was duplicated": "DEDUP",
                "No real durable connector job was claimed": "WORKER_CLAIM",
                "Durable connector result source mismatch": "JOB_SOURCE",
            }
            msg = str(error)
            if msg.startswith("Durable connector job did not succeed: "):
                reason = msg.split(": ", 1)[1]
                known = {"handler_error", "permanent_failure", "lease_expired",
                         "invalid_result", "job missing"}
                print("FAILURE_STAGE=" + ("WORKER_" + reason.upper()
                                           if reason in known else "WORKER_FAILED"))
            else:
                print("FAILURE_STAGE=" + static.get(msg, "UNCLASSIFIED_ASSERTION"))
        print("PRODUCTION_CHANGED=NO")
        return 1
    print("RU_CHECHNYA_FABRIKANT_LIVE_WORKER_EVIDENCE=" + json.dumps(evidence, sort_keys=True))
    print("RU_CHECHNYA_FABRIKANT_LIVE_WORKER=PASS")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
