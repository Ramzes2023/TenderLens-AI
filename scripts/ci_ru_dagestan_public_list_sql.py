"""Real Dagestan public JSON -> leased fenced worker -> disposable SQL -> search.

Research only: original list fields authentic, individual detail unavailable/login.
No production catalog registration, no notifications, no deployment or credentials.
"""
import asyncio
import json
import re
import tempfile
from pathlib import Path

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobSettings
from app.jobs.models import JobScope
from app.jobs.worker import Worker
from app.sources.catalog import SourceCatalog
from app.sources.ingestion import JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService, connector_version
from app.sources.multi import MultiSourceFetcher
from app.sources.opportunities import OpportunityRepository
from app.sources.registry import SourceCapabilities, SourceRegistration, SourceRegistry, SourceTransport
from app.sources.ru_dagestan_public_list import (
    SOURCE_ID, GRID, HOST, DagestanPublicListResearchSource,
)
from app.sources.snapshots import snapshot_catalog


def make_research_catalog():
    reg = SourceRegistry([SourceRegistration(
        key=SOURCE_ID,
        display_name="Дагестан — анонимный публичный реестр (без деталей)",
        source=DagestanPublicListResearchSource(timeout=25),
        transport=SourceTransport.API,
        jurisdictions=("RU",),
        languages=("ru",),
        homepage_url=GRID,
        official=True,
        enabled=True,
        capabilities=SourceCapabilities(
            keyword_search=False, pagination=False, documents=False,
            incremental_sync=False, authentication_required=False,
        ),
    )])
    return SourceCatalog(reg, MultiSourceFetcher(reg, concurrency=1))


def proof():
    catalog = make_research_catalog()
    if SOURCE_ID not in catalog.enabled_keys:
        raise AssertionError("Isolated Dagestan research connector not present")
    with tempfile.TemporaryDirectory(prefix="valyqon-dagestan-public-list-") as tmp:
        db = Database(DatabaseSettings("ru-dagestan-research", Path(tmp) / "real.sqlite"))
        try:
            jobs = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
            jobs.initialize()
            store = OpportunityRepository(db)
            store.initialize()
            claim = ConnectorSyncService(jobs, catalog).enqueue(SOURCE_ID)
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=2))
            if not Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once():
                raise AssertionError("No claimed genuine Dagestan list job")
            completed = jobs.get(claim.id, scope=JobScope())
            if completed is None or completed.state != "succeeded":
                code = completed.failure_code if completed else "missing"
                raise AssertionError("Live Dagestan list worker failure:" + str(code))
            stats = completed.result
            if (stats["fetched_count"] != 2 or stats["accepted_count"] != 2 or
                    stats["inserted_count"] != 2 or stats["skipped_count"] != 0):
                raise AssertionError("Native list worker accepted/inserted count mismatch")
            rows = store.read(SOURCE_ID, limit=2)
            if len(rows) != 2 or len({n.external_id for n in rows}) != 2:
                raise AssertionError("No two SQL-original list identities")
            snapshot = snapshot_catalog(catalog, store)
            for notice in rows:
                if (notice.url != GRID or notice.region != "Республика Дагестан"
                        or not re.fullmatch(r"[0-9]{6,12}", notice.external_id)
                        or not notice.tender_number or not notice.customer):
                    raise AssertionError("Untrusted SQL notice source provenance")
                # Real tenant keyword selection uses the stored title plus native
                # identity and never submits tenant terms to the external API.
                result = asyncio.run(snapshot.fetch(
                    source_keys=(SOURCE_ID,),
                    search_terms=(notice.external_id,),
                    limit_per_source=2,
                ))
                if result.failures or not any(
                    r.identity == notice.identity and r.title == notice.title
                    for r in result.notices
                ):
                    raise AssertionError("Real Dagestan user keyword query missed native ID")
                if store.upsert(notice, connector_version(SOURCE_ID)):
                    raise AssertionError("Idempotent Dagestan replay inserted a duplicate")
            return {
                "live_official_list_rows": len(rows),
                "lease_fenced_worker_inserted": stats["inserted_count"],
                "sqlite_user_keyword_matches": len(rows),
                "idempotent": True,
                "individual_detail_independently_verified": False,
                "public_original_registry": True,
                "production_activated": False,
            }
        finally:
            db.close()


def main():
    try:
        result = proof()
    except Exception as error:
        print("RU_DAG_REAL_PUBLIC_LIST_WORKER_SQL=BLOCKED_" + type(error).__name__)
        if isinstance(error, AssertionError) and str(error).startswith(
                "Live Dagestan list worker failure:"):
            print("RU_DAG_JOB_FAILURE_CODE=" + str(error).split(":", 1)[1][:50])
        print("ORIGINAL_LOGIN_PROTECTED_DETAILS_VERIFIED=NO")
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_DAG_PUBLIC_LIST_E2E_EVIDENCE=" + json.dumps(
        result, sort_keys=True, ensure_ascii=False))
    print("RU_DAG_REAL_PUBLIC_LIST_WORKER_SQL=PASS_RESEARCH_ONLY")
    print("ORIGINAL_LOGIN_PROTECTED_DETAILS_VERIFIED=NO")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
