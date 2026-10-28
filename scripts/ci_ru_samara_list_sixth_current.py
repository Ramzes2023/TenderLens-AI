"""Real official Samara JSON LIST → leased Worker → disposable SQL → guest.

No mock/fallback/original-detail assumption. A first-party buyer-public
list itself is a legitimate source, but source-specific UI must make the
limited listing provenance explicit; deep details can require login.
Current open eligibility uses only publisher-owned closing values, with
conservative global UTC+14 cut-off if the zone is undisclosed.

This script never touches VPS or production, logs no private content,
and always fails closed without a genuinely future original-list item.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import re
import tempfile
from pathlib import Path

from app.api.guest_search_routes import search_persisted_notices
from app.api.public_source_deadline import eligible_published_deadline
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobSettings
from app.jobs.models import JobScope
from app.jobs.worker import Worker
from app.sources.ingestion import JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService
from app.sources.opportunities import OpportunityRepository
from app.sources.ru_samara_public_list import GRID, SOURCE_ID, NATIVE_NUMBER
from scripts.ci_ru_samara_public_list_sql import make_research_catalog
from scripts.verify_samara_list_sixth_candidate import verify_samara_list_candidate


def prove_live_list():
    catalog=make_research_catalog()
    if SOURCE_ID not in catalog.enabled_keys:
        raise AssertionError("Official Samara source not operator-enabled in ephemeral catalog")
    with tempfile.TemporaryDirectory(prefix="valyqon-samara-sixth-live-") as temp:
        db=Database(DatabaseSettings("samara-list-sixth",Path(temp)/"isolated.sqlite"))
        try:
            repo=JobRepository(db,JobSettings(lease_seconds=240,heartbeat_seconds=10))
            repo.initialize()
            store=OpportunityRepository(db)
            store.initialize()
            job=ConnectorSyncService(repo,catalog).enqueue(SOURCE_ID)
            handlers=HandlerRegistry()
            handlers.register(JOB_TYPE,ConnectorSyncHandler(catalog,store,max_records=30))
            if not Worker(repo,handlers,job_types=(JOB_TYPE,)).run_once():
                raise AssertionError("Actual Samara Worker did not claim source job")
            completed=repo.get(job.id,scope=JobScope())
            if not completed or completed.state!="succeeded":
                raise AssertionError("Official Samara list Worker was not successful")
            rows=store.read(SOURCE_ID,limit=30)
            if len(rows)<2 or len(rows)>30:
                raise AssertionError("No two first-party native list rows available")
            if len({r.external_id for r in rows})!=len(rows):
                raise AssertionError("Duplicate first-party list IDs in SQL")
            if len({r.tender_number for r in rows})!=len(rows):
                raise AssertionError("Duplicate first-party list numbers in SQL")
            now=datetime.now(timezone.utc)
            open_rows=[]
            for notice in rows:
                if (notice.url!=GRID
                    or notice.region!="Самарская область"
                    or re.fullmatch(r"[0-9]{6,12}",notice.external_id) is None
                    or NATIVE_NUMBER.fullmatch(notice.tender_number or "") is None
                    or not notice.title or not notice.customer):
                    raise AssertionError("Untrusted first-party public-list provenance")
                if eligible_published_deadline(SOURCE_ID,notice.deadline,now=now):
                    open_rows.append(notice)
            if not open_rows:
                raise AssertionError("No safely current native public-list deadlines")

            candidate=verify_samara_list_candidate(db,now=now)
            if candidate["safely_open_public_list_rows"]!=len(open_rows):
                raise AssertionError("SQL candidate gate failed actual Worker current rows")
            for notice in open_rows[:3]:
                words=re.findall(r"[А-Яа-яЁёA-Za-z]{5,}",notice.title)
                if not words:
                    raise AssertionError("Live notice title does not admit searchable keyword")
                guest=search_persisted_notices(db,words[0],active_only=True,now=now)
                preview=next((r for r in guest["results"]
                              if r["title"]==notice.title),None)
                if preview is None or preview["deadline"]!=notice.deadline:
                    raise AssertionError("Source-owned live deadline/title not found by guest")
                if set(preview)!={"title","initial_price","currency","deadline"}:
                    raise AssertionError("Guest preview leaked private or deep detail fields")
            # The same source listing is idempotent in SQLite; no false
            # second-source count for EIS crossposts.
            from app.sources.ingestion import connector_version
            for notice in rows:
                if store.upsert(notice,connector_version(SOURCE_ID)):
                    raise AssertionError("Native list source produced duplicate on replay")
            return {"source":SOURCE_ID,
                    "publisher_list_records_persisted":len(rows),
                    "safely_current_list_notices":len(open_rows),
                    "guest_keyword_matches_checked":min(len(open_rows),3),
                    "first_party_public_grid":True,
                    "individual_deep_details_verified":False,
                    "idempotent":True,
                    "production_changed":False}
        finally:
            db.close()


def main():
    try:
        proof=prove_live_list()
    except Exception as exc:
        print("RU_SAMARA_SIXTH_CURRENT_LIST=BLOCKED")
        print("BLOCKER_CLASS="+type(exc).__name__)
        print("PUBLISHER_DEEP_DETAILS_VERIFIED=NO")
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_SAMARA_SIXTH_REAL_WORKER="+json.dumps(proof,sort_keys=True))
    print("RU_SAMARA_SIXTH_CURRENT_LIST=PASS_LIST_ONLY")
    print("PUBLISHER_DEEP_DETAILS_VERIFIED=NO")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
