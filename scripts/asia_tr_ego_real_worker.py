"""EGO actual published e-tenders -> genuine Worker → SQLite → snapshot search."""
from __future__ import annotations
import asyncio,json,os,tempfile
from pathlib import Path
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry,JobRepository,JobService
from app.jobs.worker import Worker
from app.sources.catalog import build_source_catalog
from app.sources.tr_ego_transport import SOURCE_ID
from app.sources.ingestion import JOB_TYPE,SYSTEM_SCOPE,ConnectorSyncHandler,ConnectorSyncService
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from scripts.asia_six_live_acceptance import settings

def main():
 if os.environ.get("VALYQON_ASIA_TURKEY_EGO_ENABLED")!="1":
  print("TR_EGO_REAL_GATE=DISABLED");return 3
 proof={"job":"NOT_STARTED","stored":0,"searched":0,"deduped":False}
 try:
  with tempfile.TemporaryDirectory(prefix="valyqon-ego-real-") as directory:
   db=Database(DatabaseSettings("tr-ego-ephemeral",Path(directory)/"notices.db"))
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
     state=jobs.get(job.id,scope=SYSTEM_SCOPE)
     proof["job"]=state.state if state else "NO_JOB"
     if proof["job"]=="succeeded":
      rows=store.read(SOURCE_ID,limit=20)
      proof["stored"]=len(rows)
      snap=snapshot_catalog(catalog,store)
      for n in rows:
       result=asyncio.run(snap.fetch(source_keys=(SOURCE_ID,),
         search_terms=(n.tender_number,),limit_per_source=20))
       if (not result.failures and len(result.notices)==1
           and result.notices[0].identity==n.identity
           and result.notices[0].url==n.url):
        proof["searched"]+=1
      proof["deduped"]=service.enqueue(SOURCE_ID).id==job.id
   finally:db.close()
 except Exception as exc:
  proof["job"]="BLOCKED"
  proof["error_type"]=type(exc).__name__
 good=(proof["job"]=="succeeded" and proof["stored"]>0
    and proof["searched"]==proof["stored"] and proof["deduped"])
 print("TR_EGO_REAL_OFFICIAL_TRANSPORT_TENDERS="+json.dumps(proof,sort_keys=True))
 print("TR_EGO_REAL_WORKER_SEARCH="+("PASS" if good else "FAIL"))
 print("PRODUCTION_CHANGED=NO")
 return 0 if good else 3
if __name__=="__main__":
 raise SystemExit(main())
