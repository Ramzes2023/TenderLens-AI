"""Actual India ePublishing → official listed bids → connector Worker → SQLite → keyword search.

Uses real public source, no mocked HTTP, no credentials, no production DB.
Source's temporary detail link is checked upstream but never persisted.
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
from app.sources.india_epublish import SOURCE_ID
from app.sources.ingestion import JOB_TYPE,SYSTEM_SCOPE,ConnectorSyncHandler,ConnectorSyncService
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from scripts.asia_six_live_acceptance import settings


def main():
    if os.environ.get("VALYQON_ASIA_INDIA_EPUBLISH_ENABLED")!="1":
        print("INDIA_EPUBLISH_GATE=NOT_ENABLED")
        return 3
    result={"job":"NOT_STARTED","stored":0,"searched":0,"duplicate_job":False}
    try:
        with tempfile.TemporaryDirectory(prefix="valyqon-india-epublish-real-") as temp:
            db=Database(DatabaseSettings("india-epublish-disposable",Path(temp)/"tenders.sqlite"))
            try:
                jobs=JobRepository(db);jobs.initialize()
                store=OpportunityRepository(db);store.initialize()
                catalog=build_source_catalog(settings())
                service=ConnectorSyncService(JobService(jobs),catalog)
                registry=HandlerRegistry()
                registry.register(JOB_TYPE,ConnectorSyncHandler(catalog,store,max_records=10))
                worker=Worker(jobs,registry,job_types=(JOB_TYPE,))
                job=service.enqueue(SOURCE_ID)
                if worker.run_once():
                    state=jobs.get(job.id,scope=SYSTEM_SCOPE)
                    result["job"]=state.state if state else "NO_JOB_RESULT"
                    if result["job"]=="succeeded":
                        notices=store.read(SOURCE_ID,limit=20)
                        result["stored"]=len(notices)
                        snapshot=snapshot_catalog(catalog,store)
                        for notice in notices:
                            fetched=asyncio.run(snapshot.fetch(
                                source_keys=(SOURCE_ID,),
                                search_terms=(notice.external_id,),
                                limit_per_source=20,
                            ))
                            if (not fetched.failures and len(fetched.notices)==1 and
                                    fetched.notices[0].identity==notice.identity and
                                    fetched.notices[0].tender_number==notice.tender_number and
                                    fetched.notices[0].url==notice.url):
                                result["searched"]+=1
                        result["duplicate_job"]=service.enqueue(SOURCE_ID).id==job.id
            finally:
                db.close()
    except Exception as exc:
        result["job"]="BLOCKED"
        result["error_type"]=type(exc).__name__
    accepted=(result["job"]=="succeeded" and result["stored"]>0 and
              result["stored"]==result["searched"] and result["duplicate_job"])
    print("INDIA_EPUBLISH_REAL_WORKER_EVIDENCE="+json.dumps(result,sort_keys=True))
    print("INDIA_EPUBLISH_REAL_STORED_SEARCH="+("PASS" if accepted else "FAIL"))
    print("PRODUCTION_CHANGED=NO")
    return 0 if accepted else 3
if __name__=="__main__":
    raise SystemExit(main())
