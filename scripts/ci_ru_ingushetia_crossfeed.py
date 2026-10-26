"""Live same-original EIS/Fabrikant Worker SQL and notification dedup proof.

Numbers come from today's real vendor listing, never a seeded ID list.
No production database, bot credentials, or Telegram API sends are used.
"""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from urllib.parse import urlencode

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobSettings
from app.jobs.models import JobScope
from app.jobs.worker import Worker
from app.monitoring.repository import MonitoringRepository
from app.monitoring.service import TenderMonitorService, prefilter_notice
from app.sources.catalog import build_source_catalog
from app.sources.eis_rss import EIS_EXTENDED_RSS_URL
from app.sources.ingestion import JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService
from app.sources.opportunities import OpportunityRepository
from app.sources.ru_dedup import deduplicate
from app.sources.ru_ingushetia_fabrikant44 import SOURCE_ID
from scripts.ci_ru_ingushetia_live_worker import ROOT, _catalog_settings, _check_isolated_dispatch


def proof():
    cfg = replace(_catalog_settings(), ru_ingushetia_eis44_enabled=False,
                  ru_ingushetia_fabrikant44_enabled=True, max_items=2)
    vendor_catalog = build_source_catalog(cfg)
    originals = asyncio.run(vendor_catalog.registry.get(SOURCE_ID).source.fetch(limit=2))
    numbers = {n.tender_number for n in originals}
    if len(numbers) != 2:
        raise AssertionError("Two live independently verified vendor originals required")
    urls = tuple(EIS_EXTENDED_RSS_URL + "?" + urlencode({
        "fz44": "on", "searchString": n.tender_number, "pageNumber": "1",
    }) for n in originals)
    catalog = build_source_catalog(replace(cfg, eis_rss_urls=urls, eis_direct_enabled=True,
                                          ca_bundle_file=ROOT))
    with tempfile.TemporaryDirectory(prefix="ingushetia-live-crossfeed-") as tmp:
        db = Database(DatabaseSettings("isolated-crossfeed", Path(tmp) / "worker.sqlite"))
        try:
            jobs = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
            jobs.initialize()
            store = OpportunityRepository(db)
            store.initialize()
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=2))
            states = {}
            for key in (SOURCE_ID, "eis"):
                job = ConnectorSyncService(jobs, catalog).enqueue(key)
                if not Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once():
                    raise AssertionError("Crossfeed Worker did not claim job")
                done = jobs.get(job.id, scope=JobScope())
                if done is None or done.state != "succeeded":
                    raise AssertionError("Crossfeed Worker failed for " + key)
                states[key] = done.state
            vendor = store.read(SOURCE_ID, limit=2)
            eis = store.read("eis", limit=2)
            if any({n.tender_number for n in rows} != numbers for rows in (vendor, eis)):
                raise AssertionError("Same live originals missing from Worker SQL")
            unique, duplicates = deduplicate(eis + vendor)
            if len(unique) != 2 or len(duplicates) != 2:
                raise AssertionError("Live crossfeed duplicate results were not collapsed")
            monitor_path = Path(tmp) / "monitor.sqlite"
            ack = asyncio.run(_check_isolated_dispatch(
                vendor_catalog, cfg, vendor, monitor_path, repository=store, source_id=SOURCE_ID,
            ))
            repo = MonitoringRepository(monitor_path)
            repo.initialize()
            service = TenderMonitorService(cfg, None, repo, None)
            repeated = asyncio.run(service.unseen_matches(101, [prefilter_notice(n, None) for n in eis]))
            if ack != 2 or repeated:
                raise AssertionError("Same EIS original would notify twice after mirror acknowledgement")
            return {"live_original_numbers": sorted(numbers), "worker_states": states,
                    "sql_rows": len(eis) + len(vendor), "unique_results": len(unique),
                    "simulated_acknowledgements": ack, "repeat_eis_alerts": len(repeated),
                    "real_telegram_delivery_proven": False, "production_changed": False}
        finally:
            db.close()


if __name__ == "__main__":
    print("INGUSHETIA_LIVE_CROSSFEED=" + json.dumps(proof(), sort_keys=True))
