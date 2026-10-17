"""LIVE Ankara public detail → lease-fenced real Worker → disposable DB → searched notice.

No mocks, no login, no production connection, no generated tender fixtures.
"""
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
from app.sources.tr_ankara_municipality import SOURCE_ID
from app.sources.ingestion import JOB_TYPE,SYSTEM_SCOPE,ConnectorSyncHandler,ConnectorSyncService
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from scripts.asia_six_live_acceptance import settings

def main():
    if os.environ.get("VALYQON_ASIA_TURKEY_ANKARA_ENABLED")!="1":
        print("TR_ANKARA_REAL_GATE=NOT_ENABLED")
        return 3
    result={"job":"NOT_STARTED","stored":0,"searched":0,"deduped":False}
    try:
        with tempfile.TemporaryDirectory(prefix="valyqon-ankara-real-") as directory:
            db=Database(DatabaseSettings("tr-ankara-ephemeral",Path(directory)/"source.sqlite"))
            try:
                jobs=JobRepository(db);jobs.initialize()
                store=OpportunityRepository(db);store.initialize()
                catalog=build_source_catalog(settings())
                service=ConnectorSyncService(JobService(jobs),catalog)
                handlers=HandlerRegistry()
                handlers.register(JOB_TYPE,ConnectorSyncHandler(catalog,store,max_records=4))
                worker=Worker(jobs,handlers,job_types=(JOB_TYPE,))
                job=service.enqueue(SOURCE_ID)
                if worker.run_once():
                    completed=jobs.get(job.id,scope=SYSTEM_SCOPE)
                    result["job"]=completed.state if completed else "NO_JOB"
                    if result["job"]!="succeeded":
                        result["failure_code"]=completed.failure_code if completed else None
                        try:
                            from app.sources.tr_ankara_municipality import (
                                _fetch, INDEX_URL, listing_detail_links, parse_ankara_tender,
                            )
                            page=asyncio.run(_fetch(INDEX_URL,25.0,"text/html"))
                            links=listing_detail_links(page)
                            result["index_links"]=len(links)
                            sample=asyncio.run(_fetch(links[0],25.0,"text/html"))
                            notice=parse_ankara_tender(sample,detail_url=links[0])
                            result["first_detail_verifiable"]=notice is not None
                        except Exception as ex:
                            # Only source-controlled exception class and bounded public message.
                            result["source_rejection_type"]=type(ex).__name__
                            result["source_rejection_reason"]=str(ex)[:180]
                    if result["job"]=="succeeded":
                        notices=store.read(SOURCE_ID,limit=20)
                        result["stored"]=len(notices)
                        snapshot=snapshot_catalog(catalog,store)
                        for n in notices:
                            found=asyncio.run(snapshot.fetch(
                                source_keys=(SOURCE_ID,),
                                search_terms=(n.tender_number,),limit_per_source=20))
                            if (not found.failures and len(found.notices)==1
                                    and found.notices[0].identity==n.identity
                                    and found.notices[0].url==n.url
                                    and found.notices[0].deadline==n.deadline):
                                result["searched"]+=1
                        result["deduped"]=service.enqueue(SOURCE_ID).id==job.id
            finally:
                db.close()
    except Exception as ex:
        result["job"]="BLOCKED"
        result["error_type"]=type(ex).__name__
    good=(result["job"]=="succeeded" and result["stored"]>0
          and result["stored"]==result["searched"] and result["deduped"])
    print("TR_ANKARA_REAL_GOVERNMENT_EVIDENCE="+json.dumps(result,sort_keys=True))
    print("TR_ANKARA_REAL_WORKER_SEARCH="+("PASS" if good else "FAIL"))
    print("PRODUCTION_CHANGED=NO")
    return 0 if good else 3
if __name__=="__main__":
    raise SystemExit(main())
