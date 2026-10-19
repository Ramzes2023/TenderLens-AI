"""Fail-closed real B2B-Center -> actual connector worker -> disposable DB -> query.

This is a live acceptance test; no fixtures, credentials, production database or
LLM APIs. It fails rather than treating an unreachable site as 'green'.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import connector_version
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from app.jobs import HandlerRegistry, JobRepository, JobSettings
from app.jobs.models import JobScope
from app.jobs.worker import Worker
from app.sources.ingestion import ConnectorSyncHandler, ConnectorSyncService, JOB_TYPE

SOURCE = "b2b_center"
MAX_RECORDS = 10


def b2b_settings():
    return MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=MAX_RECORDS,
        max_notifications_per_cycle=5, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        eis_223_enabled=False, b2b_center_enabled=True,
    )


def ingest_live_b2b(db, catalog, store):
    """One durable job, at most three attempts; honor real queue backoff.

    Only retryable handler failures return to queued. Each claim retains the
    production exact-host, TLS, public-IP, two-request and 2 MiB limits.
    """
    jobs = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
    jobs.initialize()
    job = ConnectorSyncService(jobs, catalog).enqueue(SOURCE)
    handlers = HandlerRegistry()
    handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=MAX_RECORDS))
    worker = Worker(jobs, handlers, job_types=(JOB_TYPE,))
    deadline = time.monotonic() + 165
    while time.monotonic() < deadline:
        current = jobs.get(job.id, scope=JobScope())
        if current.state == 'succeeded':
            result = current.result
            if not isinstance(result, dict) or result.get('source_id') != SOURCE:
                raise AssertionError('Durable connector result source mismatch')
            print('B2B_CONNECTOR_ATTEMPTS=' + str(current.attempt_count), flush=True)
            return result
        if current.state != 'queued':
            print('B2B_CONNECTOR_ATTEMPTS=' + str(current.attempt_count), flush=True)
            print('B2B_CONNECTOR_STATE=' + current.state, flush=True)
            raise AssertionError('Durable connector job did not succeed: ' +
                                 str(current.failure_code))
        if not worker.run_once():
            time.sleep(.25)
    raise AssertionError('Durable connector retry deadline exceeded')


def _verified_b2b_public_url(notice):
    """Require canonical original B2B public URL and its stored exact identity.

    The legacy public /search/number/ and first-party Next-market procedure
    pages are separate, verified URL contracts, never aggregate relabeling.
    """
    import re
    from app.sources.b2b_next_market import native_url
    from app.sources.eis_rss import SourceError

    if notice.source != SOURCE or not isinstance(notice.external_id, str):
        return False
    legacy = re.fullmatch(
        r"https://www[.]b2b-center[.]ru/search/number/([a-zA-Z0-9-]{1,500})/",
        notice.url,
    )
    if legacy:
        return legacy.group(1) == notice.external_id
    try:
        canonical, original_number = native_url(notice.url)
    except SourceError:
        return False
    return (canonical == notice.url and original_number == notice.external_id
            and notice.tender_number == original_number)

def acceptance() -> dict[str, int | bool]:
    # This settings object is intentionally independent of the operator's .env.
    settings = b2b_settings()
    catalog = build_source_catalog(settings)
    if SOURCE not in catalog.enabled_keys:
        raise AssertionError("B2B-Center not enabled in test catalog")

    with tempfile.TemporaryDirectory(prefix="valyqon-real-ru-worker-") as directory:
        db = Database(DatabaseSettings("ru-real-worker-acceptance", Path(directory) / "live.sqlite"))
        try:
            store = OpportunityRepository(db)
            store.initialize()
            report = ingest_live_b2b(db, catalog, store)
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
                if not _verified_b2b_public_url(notice):
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
            print('B2B_WORKER_SEARCH_IDENTITIES=' + json.dumps(
                [n.url for n in notices]), flush=True)
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

        # Report only explicitly coded assertion messages or durable failure codes.
        allowed = {
            "Real worker ingestion did not persist every public notice",
            "Persisted notice count mismatch",
            "Real notice identities not unique",
            "Stored source and public URL mismatch",
            "Real stored notice not searchable by identity",
            "Replay inserted duplicate source identity",
            "Incomplete DB -> keyword search roundtrip",
            "No real durable connector job was claimed",
            "Durable connector result source mismatch",
        }
        reason = str(error)
        if type(error) is AssertionError:
            if reason.startswith("Durable connector job did not succeed: "):
                code = reason.rsplit(": ", 1)[-1]
                if code in {"handler_error","permanent_failure","lease_expired","invalid_result","job missing"}:
                    print("FAILURE_STAGE=LEASED_WORKER_" + code.upper(), flush=True)
            elif reason in allowed:
                print("FAILURE_STAGE=" + reason.replace(" ", "_")[:100], flush=True)
        print("PRODUCTION_CHANGED=NO", flush=True)
        return 1
    print("RU_B2B_REAL_WORKER_GATE=PASS", flush=True)
    print("RU_B2B_WORKER_EVIDENCE=" + json.dumps(evidence, sort_keys=True), flush=True)
    print("PRODUCTION_CHANGED=NO", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
