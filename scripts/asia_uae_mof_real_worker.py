"""Actual UAE MoF federal RFQs → real lease-fenced worker → temporary DB → stored search."""
import asyncio
import json
import os
import tempfile
from pathlib import Path

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobService
from app.jobs.worker import Worker
from app.sources.catalog import build_source_catalog
from app.sources.uae_mof_rfqs import SOURCE_ID
from app.sources.ingestion import JOB_TYPE,SYSTEM_SCOPE,ConnectorSyncHandler,ConnectorSyncService
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from scripts.asia_six_live_acceptance import settings


def main():
    if os.environ.get("VALYQON_ASIA_UAE_FEDERAL_ENABLED")!="1":
        print("UAE_FEDERAL_OFFICIAL_LIVE_GATE=DISABLED")
        return 3
    result={"job":"NOT_STARTED","stored":0,"searched":0,"deduped":False}
    try:
        with tempfile.TemporaryDirectory(prefix="valyqon-uae-federal-real-") as path:
            db=Database(DatabaseSettings("uae-official-ephemeral",Path(path)/"tenders.sqlite"))
            try:
                jobs=JobRepository(db);jobs.initialize()
                store=OpportunityRepository(db);store.initialize()
                catalog=build_source_catalog(settings())
                queue=ConnectorSyncService(JobService(jobs),catalog)
                handlers=HandlerRegistry()
                handlers.register(JOB_TYPE,ConnectorSyncHandler(catalog,store,max_records=10))
                worker=Worker(jobs,handlers,job_types=(JOB_TYPE,))
                job=queue.enqueue(SOURCE_ID)
                if worker.run_once():
                    finished=jobs.get(job.id,scope=SYSTEM_SCOPE)
                    result["job"]=finished.state if finished else "NO_JOB"
                    if result["job"]=="succeeded":
                        notices=store.read(SOURCE_ID,limit=20)
                        result["stored"]=len(notices)
                        snapshot=snapshot_catalog(catalog,store)
                        for notice in notices:
                            report=asyncio.run(snapshot.fetch(
                                source_keys=(SOURCE_ID,),search_terms=(notice.external_id,),
                                limit_per_source=20))
                            if (not report.failures and len(report.notices)==1 and
                                    report.notices[0].identity==notice.identity and
                                    report.notices[0].deadline==notice.deadline and
                                    report.notices[0].url==notice.url):
                                result["searched"]+=1
                        result["deduped"]=queue.enqueue(SOURCE_ID).id==job.id
            finally:
                db.close()
    except Exception as exc:
        result["job"]="BLOCKED"
        result["error_type"]=type(exc).__name__
    verified=(result["job"]=="succeeded" and result["stored"]>0 and
              result["stored"]==result["searched"] and result["deduped"])
    print("UAE_FEDERAL_MOF_REAL_WORKER_EVIDENCE="+json.dumps(result,sort_keys=True))
    print("UAE_FEDERAL_MOF_PERSISTED_SEARCH="+("PASS" if verified else "FAIL"))
    print("PRODUCTION_CHANGED=NO")
    return 0 if verified else 3
if __name__=="__main__":
    raise SystemExit(main())
