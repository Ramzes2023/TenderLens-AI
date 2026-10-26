"""Real Azerbaijan Deposit Insurance Fund public procurement -> leased worker -> disposable SQLite -> saved-search proof.

NO mocks, no production database, no credentials or automatic enablement.
A separate invocation verifies exactly one source; failure must be visible.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobService
from app.jobs.worker import Worker
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import SourceCatalog, build_source_catalog
from app.sources.eis_rss import SourceError
from app.sources.ingestion import (
    HOSTS, JOB_TYPE, SYSTEM_SCOPE, ConnectorSyncHandler, ConnectorSyncService,
)
from app.sources.multi import MultiSourceFetcher
from app.sources.opportunities import OpportunityRepository
from app.sources.registry import SourceRegistry
from app.sources.snapshots import snapshot_catalog
from scripts.cis_live_source_evidence import classify_source_batch


def verify(source_id):
    # Import canonical main-branch source and worker contracts; only in-memory
    # test catalog registration is enabled, never global/source configuration.
    settings = MonitoringSettings(False, 600, 20, 5, 12, (), None)
    canonical = build_source_catalog(settings)
    registration = canonical.registry.get(source_id)
    if registration.enabled or not registration.official:
        raise AssertionError("State entity source must be officially registered and disabled by default")
    if source_id not in HOSTS or len(HOSTS[source_id]) != 1:
        raise AssertionError("Unexpected transport host allowlist")
    enabled = SourceRegistry((replace(registration, enabled=True),))
    catalog = SourceCatalog(enabled, MultiSourceFetcher(enabled, concurrency=1))

    with tempfile.TemporaryDirectory(prefix="valyqon-az-adif-small-live-") as temporary:
        db = Database(DatabaseSettings("", Path(temporary) / "cis-acceptance.sqlite"))
        try:
            jobs = JobRepository(db)
            jobs.initialize()  # real migrations, no existing DB
            notices = OpportunityRepository(db)
            notices.initialize()
            service = ConnectorSyncService(JobService(jobs), catalog)
            claimable = service.enqueue(source_id)
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, notices, max_records=20))
            # Respect the durable queue's *existing* bounded three-attempt
            # retry policy. Transient official HTTPS failures may recover a few
            # seconds later; do not fabricate or accept any missing records.
            # Permanent source/schema/storage failures must remain red.
            final = None
            for attempt in range(3):
                if not Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once():
                    raise AssertionError("No source job claimed by live worker")
                final = jobs.get(claimable.id, scope=SYSTEM_SCOPE)
                if final is None or final.state == "succeeded":
                    break
                if (final.state != "queued" or final.failure_code != "handler_error"
                        or final.attempt_count >= final.max_attempts or attempt == 2):
                    break
                # The repository stores microsecond UTC availability. Wait only
                # until its real retry slot; never backdate or bypass the lease.
                wait = final.available_at / 1_000_000 - time.time()
                time.sleep(min(4.0, max(0.1, wait + 0.15)))

            if final is None or final.state != "succeeded" or not isinstance(final.result, dict):
                diagnostics = {"source": source_id, "passed": False,
                               "failed_at": "lease_or_live_acquisition",
                               "job_state": final.state if final else "missing",
                               "attempts": final.attempt_count if final else 0,
                               "safe_failure_code": final.failure_code if final else None}
                # A one-notice direct official HTTPS probe diagnoses transport
                # versus HTML schema without logging a response, URL query,
                # exception body, credentials, or disabling TLS verification.
                try:
                    probe_rows = asyncio.run(registration.source.fetch(1))
                except Exception as exc:
                    diagnostics["source_probe_error_type"] = type(exc).__name__
                    if isinstance(exc, SourceError):
                        diagnostics["source_probe_safe_reason"] = str(exc)[:120]
                else:
                    diagnostics["source_probe_rows"] = len(probe_rows)
                return diagnostics

            stored = notices.read(source_id, limit=100)
            # Success is not synonymous with >0 currently open bids.
            # The official ADIF parser *first* verifies dated procurement
            # articles and only then returns [] when their bid windows closed.
            batch_state = classify_source_batch(source_id, final.result, stored)
            if batch_state == "verified_empty":
                with db.connect() as conn:
                    count = conn.execute(
                        "SELECT COUNT(*) FROM source_opportunities WHERE source_id=?",
                        (source_id,)).fetchone()[0]
                if count != 0:
                    raise AssertionError("Empty ADIF Worker leaked persisted tenders")
                negative = asyncio.run(snapshot_catalog(catalog, notices).fetch(
                    source_keys=(source_id,), limit_per_source=20,
                    search_terms=("valyqon_adif_verified_empty_93419522",),
                ))
                if negative.failures or negative.notices:
                    raise AssertionError("Empty ADIF search leaked opportunities")
                return {
                    "source": source_id, "passed": True,
                    "source_status": "VERIFIED_EMPTY",
                    "worker_completed": True, "active_offer_count": 0,
                    "active_tender_delivery_verified": False,
                    "official_page_validated_by_strict_parser": True,
                    "empty_source_search_verified": True,
                    "production_source_remains_disabled": True,
                }
            with db.connect() as conn:
                rows = conn.execute("SELECT source_id, external_id, connector_version FROM source_opportunities WHERE source_id=?", (source_id,)).fetchall()
            if len(rows) != len(stored):
                raise AssertionError("Persisted row count mismatch")
            if any(n.source != source_id or urlsplit(n.url).hostname not in HOSTS[source_id] or not n.title.strip() for n in stored):
                raise AssertionError("Untrusted source identity, URL, or empty title")
            if any(row[2] != final.result.get("source_id", source_id) and not str(row[2]).startswith("connector-sync-v1:" + source_id + ":") for row in rows):
                raise AssertionError("Unexpected connector provenance")

            # Verify actual search, not just HTTP or a mocked repository.
            search_term = stored[0].title.strip().split()[0]
            result = asyncio.run(snapshot_catalog(catalog, notices).fetch(
                source_keys=(source_id,), limit_per_source=20,
                search_terms=(search_term,),
            ))
            if result.failures or not any(n.identity == stored[0].identity for n in result.notices):
                raise AssertionError("Authenticated-search storage path missing saved notice")
            if len({x.url for x in stored}) != len(stored):
                raise AssertionError("Shared vendor form incorrectly counted as independent procurement")
            if any(n.initial_price is not None or n.currency is not None for n in stored):
                raise AssertionError("Unknown official tender budgets may not be invented")
            return {"source": source_id, "passed": True,
                    "source_status": "ACTIVE",
                    "stored_notices": len(stored),
                    "snapshot_matches": len(result.notices),
                    "active_tender_delivery_verified": True,
                    "identity_verified": True,
                    "production_source_remains_disabled": True}
        finally:
            db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, choices=("az_adif_small",))
    args = parser.parse_args()
    try:
        result = verify(args.source)
    except Exception as exc:
        # Never emit HTTP response, upstream HTML or secrets in CI logs.
        result = {"source": args.source, "passed": False,
                  "failed_at": "live_or_storage_validation", "failure_type": type(exc).__name__}
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
