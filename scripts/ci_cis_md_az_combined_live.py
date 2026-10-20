"""Live CIS cross-source proof: MD and AZ official/public HTTPS → same fenced queue
→ shared disposable SQLite → source-specific real saved searches.

No mocks, cached fixtures, production DB, customer profiles, notifications, or secrets.
A red upstream is a red test; never quietly downgrade the acceptance.
"""
import asyncio
import json
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobService
from app.jobs.worker import Worker
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import (
    HOSTS, JOB_TYPE, SYSTEM_SCOPE, ConnectorSyncHandler, ConnectorSyncService,
)
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from scripts.cis_live_source_evidence import classify_source_batch

SOURCES = ("md_elicitatie", "az_azeristilik", "az_adif_small")


def execute():
    settings = MonitoringSettings(
        False, 600, 20, 5, 12, (), None,
        cis_md_elicitatie_enabled=True, cis_az_azeristilik_enabled=True,
        cis_az_adif_small_enabled=True,
    )
    catalog = build_source_catalog(settings)
    if not all(catalog.registry.get(source).enabled for source in SOURCES):
        raise AssertionError("All three independent operator opt-ins must be active in isolated test")
    if (HOSTS["md_elicitatie"] != frozenset({"e-licitatie.md"})
            or HOSTS["az_azeristilik"] != frozenset({"azeristilik.gov.az"})
            or HOSTS["az_adif_small"] != frozenset({"adif.gov.az"})):
        raise AssertionError("Source host policy diverged")
    with tempfile.TemporaryDirectory(prefix="valyqon-cis-md-az-shared-live-") as directory:
        db = Database(DatabaseSettings("", Path(directory) / "cis-shared.sqlite"))
        try:
            jobs = JobRepository(db)
            jobs.initialize()
            opportunities = OpportunityRepository(db)
            opportunities.initialize()
            queue = ConnectorSyncService(JobService(jobs), catalog)
            scheduled = {source: queue.enqueue(source) for source in SOURCES}
            registry = HandlerRegistry()
            registry.register(JOB_TYPE, ConnectorSyncHandler(catalog, opportunities, max_records=5))
            worker = Worker(jobs, registry, job_types=(JOB_TYPE,))
            for _ in range(12):
                current = {source: jobs.get(job.id, scope=SYSTEM_SCOPE)
                           for source, job in scheduled.items()}
                if all(job is not None and job.state == "succeeded"
                       for job in current.values()):
                    break
                if any(job is None or job.state == "failed" for job in current.values()):
                    break
                ran = worker.run_once()
                if not ran:
                    # Only wait for the durable system's real lease retry times;
                    # never alter timestamps, lease ownership, or success results.
                    outstanding = [job for job in current.values()
                                   if job and job.state == "queued"]
                    if not outstanding:
                        break
                    due = min(job.available_at for job in outstanding) / 1_000_000
                    time.sleep(min(3.0, max(0.1, due - time.time() + 0.1)))
            current = {source: jobs.get(job.id, scope=SYSTEM_SCOPE)
                       for source, job in scheduled.items()}
            if not all(job is not None and job.state == "succeeded"
                       and isinstance(job.result, dict) for job in current.values()):
                return {"passed": False, "failed_at": "actual_source_queue_or_http",
                        "states": {source: current[source].state if current[source] else "missing"
                                   for source in SOURCES}}
            counts = {}
            for source in SOURCES:
                notices = opportunities.read(source, limit=100)
                batch_state = classify_source_batch(
                    source, current[source].result, notices,
                )
                if batch_state == "verified_empty":
                    # Only ADIF can be valid-empty after all verified official
                    # public bid windows have passed. Do not invent a buyer
                    # match or claim positive end-to-end procurement delivery.
                    negative = asyncio.run(snapshot_catalog(
                        catalog, opportunities,
                    ).fetch(source_keys=(source,), limit_per_source=20,
                            search_terms=("valyqon_adif_no_open_93419522",)))
                    if negative.failures or negative.notices:
                        raise AssertionError("Empty-source tenant search leaked records")
                    counts[source] = {
                        "stored": 0, "buyer_matches": 0,
                        "state": "VERIFIED_EMPTY",
                        "active_tender_delivery_verified": False,
                    }
                    continue
                if any(item.source != source or not item.title
                       or urlsplit(item.url).hostname not in HOSTS[source]
                       for item in notices):
                    raise AssertionError("Source identity or URL contamination")
                sample = notices[0]
                buyer_term = (sample.customer or "").strip()
                if not buyer_term:
                    raise AssertionError("Public buyer missing in real notice")
                result = asyncio.run(snapshot_catalog(catalog, opportunities).fetch(
                    source_keys=(source,), limit_per_source=20,
                    search_terms=(buyer_term,),
                ))
                if result.failures or not any(n.identity == sample.identity for n in result.notices):
                    raise AssertionError("Real shared-db buyer search did not recover a notice")
                if any(n.source != source for n in result.notices):
                    raise AssertionError("Tenant-facing source filtering leaked another connector")
                counts[source] = {"stored": len(notices),
                                  "buyer_matches": len(result.notices),
                                  "state": "ACTIVE",
                                  "active_tender_delivery_verified": True}
            with db.connect() as connection:
                sources = {row[0] for row in connection.execute(
                    "SELECT DISTINCT source_id FROM source_opportunities"
                ).fetchall()}
            # A verified-empty source MUST have zero stored source IDs; the
            # two mandatory genuine positive MD/AZ feeds still need records.
            positive = {source for source in SOURCES
                        if counts[source]["state"] == "ACTIVE"}
            if sources != positive:
                raise AssertionError("Shared database has missing/extra source IDs")
            if not {"md_elicitatie", "az_azeristilik"}.issubset(positive):
                raise AssertionError("Two required actual public feeds are not ingested")
            return {"passed": True, "source_counts": counts,
                    "shared_db_separate_provenance": True,
                    "real_buyer_queries_passed": True,
                    "all_three_worker_jobs_completed": True,
                    "active_procurement_source_count": len(positive),
                    "adif_active_delivery_verified": "az_adif_small" in positive,
                    "production_config_changed": False}
        finally:
            db.close()


def main():
    try:
        result = execute()
    except Exception as error:
        result = {"passed": False, "failed_at": "real_shared_integration",
                  "failure_type": type(error).__name__}
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
