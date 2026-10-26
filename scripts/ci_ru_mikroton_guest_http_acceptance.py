"""Real MikroTon public origin -> fenced Worker -> SQLite -> FastAPI guest HTTP.

No synthetic notices, Telegram/email, test accounts, production DB, bypassed
TLS or payment. If official public site is inaccessible the run FAILS CLOSED.
This confirms the guest **preview projection**, NOT subscriber delivery.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.guest_search_routes import _public_preview
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.opportunities import OpportunityRepository
from scripts.ci_ru_leased_connector import run_leased_connector

SOURCE = "mikroton_tender"


def acceptance():
    cfg = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=8,
        max_notifications_per_cycle=2, request_timeout=15,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        mikroton_tender_enabled=True,
    )
    catalog = build_source_catalog(cfg)
    if catalog.enabled_keys != (SOURCE,):
        raise AssertionError("Unexpected source selection")
    with tempfile.TemporaryDirectory(prefix="valyqon-real-guest-api-") as directory:
        db=Database(DatabaseSettings("",Path(directory)/"real-worker.sqlite"))
        try:
            store=OpportunityRepository(db)
            store.initialize()
            report=run_leased_connector(db,catalog,store,SOURCE,max_records=8)
            if not 1 <= report["fetched_count"] <= 8:
                raise AssertionError("Official source returned no real notices")
            if report["accepted_count"] != report["fetched_count"] or report["skipped_count"]:
                raise AssertionError("Worker did not persist all authentic records")
            persisted=store.read(SOURCE,limit=8)
            if len(persisted)!=report["fetched_count"]:
                raise AssertionError("Real Worker SQL persistence mismatch")
            for item in persisted:
                if (item.source!=SOURCE or
                    item.url!=f"https://tender.mt52.ru/tenders/{item.external_id}"):
                    raise AssertionError("Official source identity mismatch")

            app=create_app(
                runtime=ApiRuntime(database=db),
                settings=ApiSettings("127.0.0.1",8000,False,None),
            )
            # ASGI TestClient calls exactly the same FastAPI handler exposed
            # by the HTTP server; no mocked endpoint or replayed response.
            with TestClient(app) as client:
                response=client.get("/api/v1/public/opportunities",headers={"Accept":"application/json"})
                if response.status_code!=200:
                    raise AssertionError("Actual public FastAPI endpoint unavailable")
                data=response.json()
                if (data.get("source")!="stored_connector_notices" or
                    data.get("details_locked") is not True or
                    not 1 <= data.get("shown",0) <= 8):
                    raise AssertionError("Guest search returned no legitimate locked results")
                expected=[]
                for notice in persisted:
                    preview=_public_preview(notice.model_dump())
                    if preview is not None:
                        expected.append(preview)
                if not expected:
                    raise AssertionError("No safe visible titles in original real notices")
                for visible in data["results"]:
                    if visible not in expected:
                        raise AssertionError("Guest API contains a non-worker/fabricated notice")
                    if set(visible)!={"title","initial_price","currency","deadline"}:
                        raise AssertionError("Guest API exposed protected details")
                qterms=[]
                for preview in expected:
                    words=re.findall(r"[A-Za-zА-Яа-яЁё]{6,}",preview["title"])
                    if words:
                        qterms.append((words[0],preview))
                if not qterms:
                    raise AssertionError("No matching search term in real visible notice titles")
                query,original=qterms[0]
                searched=client.get("/api/v1/public/opportunities",params={"q":query})
                if searched.status_code!=200 or original not in searched.json().get("results",[]):
                    raise AssertionError("Keyword from authentic notice failed public HTTP search")
                if searched.headers.get("cache-control","").startswith("no-store") is False:
                    raise AssertionError("Public real search is cacheable")
                if client.get(f"/api/v1/public/opportunities/{persisted[0].external_id}").status_code!=404:
                    raise AssertionError("Guest could open a protected tender detail route")
                if client.get("/api/v1/public/opportunities",params={"q":"valyqon_no_real_match_983417"}).json().get("shown")!=0:
                    raise AssertionError("Unrelated query returned invented/nonmatching results")
            return {
                "origin":SOURCE,
                "real_worker_written":report["accepted_count"],
                "stored_reloaded":len(persisted),
                "guest_public_rows":data["shown"],
                "keyword_http_match":True,
                "paid_details_locked":True,
                "public_private_fields_exposed":False,
                "official_telegram_delivery":False,
                "external_email_delivery":False,
                "production_changed":False,
                "evidence_level":"REAL_HTTP_TO_WORKER_DB_TO_ASGI_HTTP_GUEST_PROJECTION",
            }
        finally:
            db.close()


if __name__ == "__main__":
    try:
        evidence=acceptance()
    except Exception as exc:
        print("RU_REAL_GUEST_API=BLOCKED_OR_FAILED")
        print("FAILURE_CLASS="+type(exc).__name__)
        print("PRODUCTION_CHANGED=NO")
        raise SystemExit(2)
    print("RU_REAL_GUEST_API_EVIDENCE="+json.dumps(evidence,sort_keys=True))
    print("RU_REAL_GUEST_API=PASS_GUEST_PROJECTION_ONLY")
    print("PRODUCTION_CHANGED=NO")
