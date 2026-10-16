"""Fail-closed real B2B-Center -> actual connector worker -> disposable DB -> query.

This is a live acceptance test; no fixtures, credentials, production database or
LLM APIs. It fails rather than treating an unreachable site as 'green'.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import connector_version
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from scripts.ci_ru_leased_connector import run_leased_connector

SOURCE = "b2b_center"
MAX_RECORDS = 10


def acceptance() -> dict[str, int | bool]:
    # This settings object is intentionally independent of the operator's .env.
    settings = MonitoringSettings(
        enabled=False,
        interval_seconds=600,
        max_items=MAX_RECORDS,
        max_notifications_per_cycle=5,
        request_timeout=25,
        eis_rss_urls=(),
        ca_bundle_file=None,
        profile_feeds_enabled=False,
        eis_223_enabled=False,
        b2b_center_enabled=True,
    )
    catalog = build_source_catalog(settings)
    if SOURCE not in catalog.enabled_keys:
        raise AssertionError("B2B-Center not enabled in test catalog")

    with tempfile.TemporaryDirectory(prefix="valyqon-real-ru-worker-") as directory:
        db = Database(DatabaseSettings("ru-real-worker-acceptance", Path(directory) / "live.sqlite"))
        try:
            store = OpportunityRepository(db)
            store.initialize()
            report = run_leased_connector(db, catalog, store, SOURCE, max_records=MAX_RECORDS)
            if (
                report["fetched_count"] < 1
                or report["accepted_count"] != report["fetched_count"]
                or report["inserted_count"] != report["fetched_count"]
                or report["skipped_count"] != 0
                or report["updated_count"] != 0
            ):
                raise AssertionError("Real worker ingestion did not persist every public notice")

            notices = store.read(SOURCE, limit=MAX_RECORDS)
            if len(notices) != report["fetched_count"]:
                raise AssertionError("Persisted notice count mismatch")
            if len({n.identity for n in notices}) != len(notices):
                raise AssertionError("Real notice identities not unique")

            snapshot = snapshot_catalog(catalog, store)
            matches = 0
            for notice in notices:
                if (notice.source != SOURCE or
                        not notice.url.startswith("https://www.b2b-center.ru/search/number/")):
                    raise AssertionError("Stored source and public URL mismatch")
                result = asyncio.run(snapshot.fetch(
                    limit_per_source=MAX_RECORDS,
                    source_keys=(SOURCE,),
                    search_terms=(notice.external_id,),
                ))
                # Keyword search intentionally uses substring matching. A
                # procurement number may appear in another title or price;
                # assert the exact canonical stored identity is present.
                if (result.failures or not any(
                        candidate.identity == notice.identity and
                        candidate.url == notice.url
                        for candidate in result.notices
                )):
                    raise AssertionError("Real stored notice not searchable by identity")
                # Same-version upsert must be idempotent; no extra network call.
                if store.upsert(notice, connector_version(SOURCE)):
                    raise AssertionError("Replay inserted duplicate source identity")
                matches += 1

            if matches != report["fetched_count"]:
                raise AssertionError("Incomplete DB -> keyword search roundtrip")
            return {
                "real_notices_fetched": report["fetched_count"],
                "ingested_by_worker": report["accepted_count"],
                "new_db_records": report["inserted_count"],
                "search_verified": matches,
                "idempotent_replay": True,
                "verified_notice_detail": False,
                "production_changed": False,
            }
        finally:
            db.close()


def main() -> int:
    try:
        evidence = acceptance()
    except Exception as error:
        print("RU_B2B_REAL_WORKER_GATE=BLOCKED", flush=True)
        print("FAILURE_CLASS=" + type(error).__name__, flush=True)
        print("PRODUCTION_CHANGED=NO", flush=True)
        return 1
    print("RU_B2B_REAL_WORKER_GATE=PASS", flush=True)
    print("RU_B2B_WORKER_EVIDENCE=" + json.dumps(evidence, sort_keys=True), flush=True)
    print("PRODUCTION_CHANGED=NO", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
