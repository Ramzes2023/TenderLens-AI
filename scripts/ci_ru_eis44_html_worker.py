"""Strict live official 44-FZ EIS HTML -> canonical worker -> ephemeral search.

EIS RSS endpoints currently 404 on RU3; HTML results use an explicitly vetted
Ministry CA file, still perform full TLS validation, and never follow redirects.
Detail URLs remain unverified and are not fetched by this acceptance.
"""
import asyncio
import json
import os
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

SOURCE = "eis_44_html"


def acceptance():
    raw = os.environ.get("VALYQON_RU_EIS_CA_CERT", "").strip()
    if not raw or not Path(raw).is_file():
        raise ValueError("Explicit vetted EIS app-scoped CA is mandatory")
    settings = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=10,
        max_notifications_per_cycle=5, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=Path(raw), profile_feeds_enabled=False,
        eis_44_html_enabled=True,
    )
    catalog = build_source_catalog(settings)
    if SOURCE not in catalog.enabled_keys:
        raise AssertionError("EIS 44 official HTML not enabled")
    with tempfile.TemporaryDirectory(prefix="ru-eis44-live-worker-") as tmp:
        db = Database(DatabaseSettings("ru-eis44-html-acceptance", Path(tmp) / "notices.sqlite"))
        try:
            repo = OpportunityRepository(db)
            repo.initialize()
            info = run_leased_connector(db, catalog, repo, SOURCE, max_records=10)
            if (not 1 <= info["fetched_count"] <= 10
                    or info["accepted_count"] != info["fetched_count"]
                    or info["inserted_count"] != info["fetched_count"]
                    or info["skipped_count"] != 0):
                raise AssertionError("Not all official EIS HTML notices were inserted")
            rows = repo.read(SOURCE, limit=10)
            if len(rows) != info["fetched_count"]:
                raise AssertionError("EIS HTML durable DB mismatch")
            catalog_search = snapshot_catalog(catalog, repo)
            for item in rows:
                if not item.tender_number or item.tender_number != item.external_id:
                    raise AssertionError("Official EIS regNumber missing")
                if item.url != (
                    f"https://zakupki.gov.ru/epz/order/notice/ezt20/view/common-info.html"
                    f"?regNumber={item.external_id}"
                ) and not item.url.startswith(
                    "https://zakupki.gov.ru/epz/order/notice/"
                ):
                    raise AssertionError("EIS noncanonical detail link")
                found = asyncio.run(catalog_search.fetch(
                    source_keys=(SOURCE,),
                    search_terms=(item.external_id,),
                    limit_per_source=10,
                ))
                if found.failures or not any(
                    x.identity == item.identity and x.url == item.url
                    for x in found.notices
                ):
                    raise AssertionError("Official EIS HTML result not searchable")
                if repo.upsert(item, connector_version(SOURCE)):
                    raise AssertionError("Duplicate official EIS notice")
            return {
                "official_law_44_verified_from_cards": len(rows),
                "actual_worker_inserted": info["inserted_count"],
                "sqlite_search_verified": len(rows),
                "independent_detail_verified": False,
                "production_changed": False,
            }
        finally:
            db.close()


def main():
    try:
        result = acceptance()
    except Exception as e:
        print("RU_EIS44_HTML_REAL_WORKER=BLOCKED", flush=True)
        print("FAILURE_CLASS=" + type(e).__name__, flush=True)
        print("PRODUCTION_CHANGED=NO", flush=True)
        return 1
    print("RU_EIS44_HTML_EVIDENCE=" + json.dumps(result, sort_keys=True), flush=True)
    print("RU_EIS44_HTML_REAL_WORKER=PASS", flush=True)
    print("PRODUCTION_CHANGED=NO", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
