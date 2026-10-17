"""HKMA's ACTUAL recent official Gazette tenders -> queue -> Worker -> DB -> search.

No mocks, no local placeholder rows, no production/customer DB mutation.
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry,JobRepository,JobService
from app.jobs.worker import Worker
from app.sources.catalog import build_source_catalog
from app.sources.hk_hkma_tender import SOURCE_ID
from app.sources.ingestion import JOB_TYPE,SYSTEM_SCOPE,ConnectorSyncHandler,ConnectorSyncService
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from scripts.asia_six_live_acceptance import settings


def main():
    if os.environ.get("VALYQON_ASIA_HKMA_ENABLED")!="1":
        print("HKMA_TENDER_LIVE_GATE=DISABLED")
        return 3
    result={"job":"NOT_STARTED","stored":0,"searched":0,"replay_deduped":False}
    try:
        with tempfile.TemporaryDirectory(prefix="valyqon-hkma-real-") as temp:
            db=Database(DatabaseSettings("hkma-disposable",Path(temp)/"tenders.sqlite"))
            try:
                jobs=JobRepository(db);jobs.initialize()
                store=OpportunityRepository(db);store.initialize()
                catalog=build_source_catalog(settings())
                service=ConnectorSyncService(JobService(jobs),catalog)
                handlers=HandlerRegistry()
                handlers.register(JOB_TYPE,ConnectorSyncHandler(catalog,store,max_records=10))
                worker=Worker(jobs,handlers,job_types=(JOB_TYPE,))
                job=service.enqueue(SOURCE_ID)
                if worker.run_once():
                    completed=jobs.get(job.id,scope=SYSTEM_SCOPE)
                    result["job"]=completed.state if completed else "NO_COMPLETED_JOB"
                    if result["job"]=="succeeded":
                        stored=store.read(SOURCE_ID,limit=20)
                        result["stored"]=len(stored)
                        snapshot=snapshot_catalog(catalog,store)
                        for notice in stored:
                            found=asyncio.run(snapshot.fetch(
                                source_keys=(SOURCE_ID,),
                                search_terms=(notice.external_id,),
                                limit_per_source=20,
                            ))
                            if (not found.failures and len(found.notices)==1
                                    and found.notices[0].identity==notice.identity
                                    and found.notices[0].url==notice.url):
                                result["searched"]+=1
                        result["replay_deduped"]=service.enqueue(SOURCE_ID).id==job.id
            finally:
                db.close()
    except Exception as exc:
        result["job"]="BLOCKED"
        result["error_type"]=type(exc).__name__
    passed=(result["job"]=="succeeded" and result["stored"]>0 and
            result["searched"]==result["stored"] and result["replay_deduped"])
    print("HKMA_REAL_PUBLIC_TENDERS="+json.dumps(result,sort_keys=True))
    print("HKMA_REAL_WORKER_SEARCH="+("PASS" if passed else "FAIL"))
    print("PRODUCTION_CHANGED=NO")
    return 0 if passed else 3


if __name__=="__main__":
    raise SystemExit(main())
