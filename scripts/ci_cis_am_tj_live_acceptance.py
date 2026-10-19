"""Real public-source -> leased worker -> disposable SQLite -> saved-search proof.

NO mocks, no production database, no credentials or automatic enablement.
A separate invocation verifies exactly one source; failure must be visible.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobService
from app.jobs.worker import Worker
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import SourceCatalog, build_source_catalog
from app.sources.eis_rss import SourceError
from app.sources.ingestion import (
    HOSTS, JOB_TYPE, SYSTEM_SCOPE, ConnectorSyncHandler, ConnectorSyncService, connector_version,
)
from app.sources.multi import MultiSourceFetcher
from app.sources.opportunities import OpportunityRepository
from app.sources.registry import SourceRegistry
from app.sources.snapshots import snapshot_catalog


_SOURCE_REASONS = {
    "ARMEPS listing structure unverified or changed.": "listing_schema",
    "ARMEPS invalid listing row.": "listing_row",
    "ARMEPS unsafe or mismatched observed detail link.": "detail_link",
    "ARMEPS unverified end bid time format.": "deadline",
    "ARMEPS invalid normalized notice.": "normalized_fields",
    "ARMEPS conflicting duplicate ID.": "conflicting_duplicate",
    "ARMEPS oversized or invalid HTML.": "html_bound",
    "ARMEPS response is not HTML.": "content_type",
    "ARMEPS strict transport policy rejected request.": "transport_policy",
    "ARMEPS verified public-IP policy rejected connection.": "public_ip_policy",
    "ARMEPS unclassified HTTPS connection failure.": "https_connection",
    "ARMEPS official HTTP client status rejected.": "http_client_status",
    "Temporary source transport failure.": "transient_transport",
    "TJ listing structure unverified or changed.": "listing_schema",
    "TJ incomplete listing row.": "listing_row",
    "TJ invalid normalized public fields.": "normalized_fields",
}


def failure_chain(error):
    """Structural diagnostics from the failed worker, never exception payloads.

    Adapter/handler ``from None`` suppresses logging but preserves __context__.
    Inspect only types and exact audited markers; do not serialize messages,
    response bodies, URLs, headers, DNS addresses or arbitrary attributes.
    """
    result, seen = [], set()
    while isinstance(error, BaseException) and id(error) not in seen and len(result) < 10:
        seen.add(id(error))
        item = {"type": type(error).__name__, "module": type(error).__module__}
        if isinstance(error, httpx.HTTPStatusError):
            item["http_status"] = error.response.status_code
        if isinstance(error, httpx.ConnectError):
            item["audited_dns_marker"] = str(error) == "DNS resolution failed"
        if isinstance(error, SourceError):
            item["source_reason"] = _SOURCE_REASONS.get(str(error), "unclassified_source_error")
        result.append(item)
        error = error.__cause__ if error.__cause__ is not None else error.__context__
    return result


def run_job(jobs, handlers, job):
    """Use the queue's existing three attempts and actual availability slots."""
    final = None
    for attempt in range(3):
        if not Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once():
            raise AssertionError("No source job claimed by live worker")
        final = jobs.get(job.id, scope=SYSTEM_SCOPE)
        if final is None or final.state == "succeeded":
            break
        if (final.state != "queued" or final.failure_code != "handler_error"
                or final.attempt_count >= final.max_attempts or attempt == 2):
            break
        wait = final.available_at / 1_000_000 - time.time()
        time.sleep(min(4.0, max(0.1, wait + 0.15)))
    return final


def verify(source_id):
    # Import canonical main-branch source and worker contracts; only in-memory
    # test catalog registration is enabled, never global/source configuration.
    settings = MonitoringSettings(False, 600, 20, 5, 12, (), None)
    canonical = build_source_catalog(settings)
    registration = canonical.registry.get(source_id)
    if registration.enabled or not registration.official:
        raise AssertionError("Source should be officially registered and disabled by default")
    if source_id not in HOSTS or len(HOSTS[source_id]) != 1:
        raise AssertionError("Unexpected transport host allowlist")
    enabled = SourceRegistry((replace(registration, enabled=True),))
    catalog = SourceCatalog(enabled, MultiSourceFetcher(enabled, concurrency=1))

    with tempfile.TemporaryDirectory(prefix="valyqon-cis-live-") as temporary:
        db = Database(DatabaseSettings("", Path(temporary) / "cis-acceptance.sqlite"))
        try:
            jobs = JobRepository(db)
            jobs.initialize()  # real migrations, no existing DB
            notices = OpportunityRepository(db)
            notices.initialize()
            service = ConnectorSyncService(JobService(jobs), catalog)
            sync_time = datetime.now(timezone.utc)
            claimable = service.enqueue(source_id, now=sync_time)
            if service.enqueue(source_id, now=sync_time).id != claimable.id:
                raise AssertionError("Repeated enqueue created another job in the same window")
            handlers = HandlerRegistry()
            handler = ConnectorSyncHandler(catalog, notices, max_records=20)
            worker_failures = []
            def diagnosed_handler(context, payload):
                try:
                    return handler(context, payload)
                except Exception as error:
                    worker_failures.append(failure_chain(error))
                    raise
            handlers.register(JOB_TYPE, diagnosed_handler)
            # Respect the durable queue's *existing* bounded three-attempt
            # retry policy. Transient official HTTPS failures may recover a few
            # seconds later; do not fabricate or accept any missing records.
            # Permanent source/schema/storage failures must remain red.
            final = run_job(jobs, handlers, claimable)

            if final is None or final.state != "succeeded" or not isinstance(final.result, dict):
                diagnostics = {"source": source_id, "passed": False,
                               "failed_at": "lease_or_live_acquisition",
                               "job_state": final.state if final else "missing",
                               "attempts": final.attempt_count if final else 0,
                               "worker_failures": worker_failures,
                               "safe_failure_code": final.failure_code if final else None}
                # A one-notice direct official HTTPS probe diagnoses transport
                # versus HTML schema without logging a response, URL query,
                # exception body, credentials, or disabling TLS verification.
                try:
                    probe_rows = asyncio.run(registration.source.fetch(1))
                except Exception as exc:
                    diagnostics["source_probe_error_type"] = type(exc).__name__
                    if isinstance(exc, SourceError):
                        # Only our own static exception reason; never echo remote HTML/URL.
                        diagnostics["source_probe_safe_reason"] = str(exc)[:120]
                else:
                    diagnostics["source_probe_rows"] = len(probe_rows)
                return diagnostics

            stored = notices.read(source_id, limit=100)
            if not stored or len(stored) != len({n.identity for n in stored}):
                raise AssertionError("Empty or duplicated persisted opportunities")
            if final.result.get("accepted_count") != len(stored):
                raise AssertionError("Job result count and SQLite rows disagree")
            with closing(db.connect()) as conn:
                rows = conn.execute("SELECT source_id, external_id, connector_version FROM source_opportunities WHERE source_id=?", (source_id,)).fetchall()
            if len(rows) != len(stored):
                raise AssertionError("Persisted row count mismatch")
            if any(n.source != source_id or urlsplit(n.url).hostname not in HOSTS[source_id] or not n.title.strip() for n in stored):
                raise AssertionError("Untrusted source identity, URL, or empty title")
            if any(row[2] != connector_version(source_id) for row in rows):
                raise AssertionError("Unexpected connector provenance")

            # Each original title and number must independently find its own
            # persisted notice, including Armenian/Tajik Unicode and punctuation.
            matches = 0
            for notice in stored:
                for term in (notice.tender_number, notice.title):
                    if not term:
                        raise AssertionError("Missing original public search field")
                    result = asyncio.run(snapshot_catalog(catalog, notices).fetch(
                        source_keys=(source_id,), limit_per_source=100,
                        search_terms=(term,),
                    ))
                    if result.failures or not any(n.identity == notice.identity for n in result.notices):
                        raise AssertionError("Original number/title lookup missed persisted notice")
                    matches += 1

            # A separate sync window in this disposable queue exercises actual
            # leased upserts again. Do not change queue time, leases or retry slots.
            repeated = service.enqueue(source_id, now=sync_time + timedelta(hours=1))
            repeat = run_job(jobs, handlers, repeated)
            if repeat is None or repeat.state != "succeeded" or not isinstance(repeat.result, dict):
                return {"source": source_id, "passed": False, "failed_at": "repeat_worker",
                        "job_state": repeat.state if repeat else "missing",
                        "worker_failures": worker_failures,
                        "safe_failure_code": repeat.failure_code if repeat else None}
            after = notices.read(source_id, limit=100)
            before_ids, after_ids = {n.identity for n in stored}, {n.identity for n in after}
            if (len(after) != len(after_ids) or not before_ids <= after_ids
                    or repeat.result.get("updated_count", 0) < 1
                    or len(after) != len(stored) + repeat.result.get("inserted_count", -1)):
                raise AssertionError("Repeated ingestion lost rows or failed duplicate upsert")
            return {"source": source_id, "passed": True, "stored_notices": len(stored),
                    "original_field_searches": matches,
                    "repeat_inserted": repeat.result["inserted_count"],
                    "repeat_updated": repeat.result["updated_count"],
                    "enqueue_idempotent": True,
                    "worker_attempts": final.attempt_count,
                    "repeat_attempts": repeat.attempt_count,
                    "verified_public_examples": [
                        {"external_id": n.external_id, "number": n.tender_number,
                         "title": n.title, "url": n.url} for n in stored[:3]],
                    "identity_verified": True,
                    "production_source_remains_disabled": True}
        finally:
            db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, choices=("am_armeps", "tj_eprocurement"))
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
