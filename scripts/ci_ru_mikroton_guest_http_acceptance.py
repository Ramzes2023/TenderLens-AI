"""Real MikroTon public origin -> fenced Worker -> SQLite -> FastAPI guest HTTP.

No synthetic notices, Telegram/email, test accounts, production DB, bypassed
TLS or payment. If official public site is inaccessible the run FAILS CLOSED.
This confirms the guest **preview projection**, NOT subscriber delivery.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict
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
    if SOURCE not in catalog.enabled_keys:
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
                    preview=_public_preview(asdict(notice))
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
            # Independent authenticated tenant path: the registered company's
            # scoped 'snapshots=true' endpoint must read the SAME genuine Worker
            # SQL rows, and a non-member must not inspect its results.
            from app.auth import AuthRepository, AuthService
            from app.organizations import OrganizationRepository, OrganizationService
            from app.companies import CompanyRepository, CompanyService
            from app.monitoring import MonitoringRepository, TenderMonitorService
            from app.database import TenderRepository
            from app.api.security import SESSION_COOKIE

            auth_repo=AuthRepository(db)
            auth_repo.initialize()
            auth=AuthService(auth_repo)
            organizations=OrganizationRepository(db)
            organizations.initialize()
            company_repo=CompanyRepository(db)
            company_repo.initialize()
            monitor_repo=MonitoringRepository(db)
            monitor_repo.initialize()
            saved_repo=TenderRepository(db)
            saved_repo.initialize()
            owner=auth.register("ru-worker-owner@example.test","test account password 24680!")
            outsider=auth.register("ru-worker-outside@example.test","test account password 13579!")
            org=organizations.create("Isolated REAL_HTTP Worker QA",owner.id)
            chosen=next((term for term,preview in qterms
                         if preview in data["results"]),None)
            if chosen is None:
                raise AssertionError("No genuine title term for scoped company test")
            private_runtime=ApiRuntime(
                auth_service=auth,
                organization_service=OrganizationService(organizations),
                company_service=CompanyService(company_repo),
                tender_discovery_service=TenderMonitorService(
                    cfg, None, monitor_repo, None),
                source_catalog=catalog,
                tender_repository=saved_repo,
                database=db,
            )
            private_app=create_app(runtime=private_runtime,
                settings=ApiSettings("127.0.0.1",8000,False,None))
            with TestClient(private_app) as private:
                private.cookies.set(SESSION_COOKIE,auth.create_session(owner))
                api=f"/api/v1/organizations/{org.id}"
                profile={
                    "profile_version":"real-worker-http-acceptance-v1",
                    "company_name":"Isolated REAL_HTTP Buyer",
                    "business_mode":"sell",
                    "product_keywords":[chosen],
                    "search_keywords":[chosen],
                    "accepted_currencies":["RUB"],
                }
                company=private.post(api+"/companies",json={
                    "name":"REAL_HTTP Temporary Buyer","profile":profile})
                if company.status_code!=201:
                    raise AssertionError("Real API company registration failed")
                query_response=private.post(api+"/discover/tenders?snapshots=true")
                if query_response.status_code!=200:
                    raise AssertionError("Authenticated snapshot Discovery API failed")
                discovery=query_response.json()
                if not discovery.get("items"):
                    raise AssertionError("Real worker source produced no authenticated matches")
                source_ids={(r.source,r.external_id) for r in persisted}
                for item in discovery["items"]:
                    if (item.get("source"),item.get("external_id")) not in source_ids:
                        raise AssertionError("Discovery returned a non-worker notice")
                    if item.get("analysis_stage")!="metadata_preview":
                        raise AssertionError("Unverified AI analysis was claimed")
                matches=len(discovery["items"])
                # A real matched notice is saved through the user's actual
                # tenant-scoped HTTP route and must survive a subsequent read.
                selected=discovery["items"][0]
                saved_response=private.post(api+"/shortlist",json=selected)
                if saved_response.status_code!=200:
                    raise AssertionError("Authorized real-notice shortlist save failed")
                saved=saved_response.json()
                if (saved.get("opportunity",{}).get("external_id")!=selected["external_id"] or
                    saved.get("opportunity",{}).get("source")!=SOURCE):
                    raise AssertionError("Saved notice identity changed")
                remembered=private.get(api+"/shortlist")
                if (remembered.status_code!=200 or
                    not any(r.get("id")==saved.get("id") for r in remembered.json())):
                    raise AssertionError("Real saved notice did not persist in account shortlist")
                replay=private.post(api+"/shortlist",json=selected)
                if replay.status_code!=200 or replay.json().get("id")!=saved.get("id"):
                    raise AssertionError("Real saved opportunity is not duplicate-idempotent")
                private.cookies.clear()
                private.cookies.set(SESSION_COOKIE,auth.create_session(outsider))
                denied=private.post(api+"/discover/tenders?snapshots=true")
                if denied.status_code!=403:
                    raise AssertionError("Cross-tenant registered user could access search")
                if private.get(api+"/shortlist").status_code!=403:
                    raise AssertionError("Cross-tenant registered user could read saved genuine tenders")
            return {
                "origin":SOURCE,
                "real_worker_written":report["accepted_count"],
                "stored_reloaded":len(persisted),
                "guest_public_rows":data["shown"],
                "authenticated_company_matches":matches,
                "authorized_saved_real_notice":True,
                "saved_replay_no_duplicates":True,
                "outsider_saved_access_denied":True,
                "cross_tenant_scope_denied":True,
                "keyword_http_match":True,
                "guest_details_locked":True,
                "merchant_entitlement_verified":False,
                "commercial_release_ready":False,
                "public_private_fields_exposed":False,
                "official_telegram_delivery":False,
                "external_email_delivery":False,
                "production_changed":False,
                "evidence_level":"REAL_HTTP_TO_WORKER_DB_TO_GUEST_AND_AUTHENTICATED_ASGI_HTTP",
            }
        finally:
            db.close()


if __name__ == "__main__":
    try:
        evidence=acceptance()
    except Exception as exc:
        print("RU_REAL_GUEST_API=BLOCKED_OR_FAILED")
        print("FAILURE_CLASS="+type(exc).__name__)
        # All AssertionErrors in this test have short hardcoded diagnostic
        # messages; never print arbitrary transport exceptions, tokens or URLs.
        if type(exc) is AssertionError and str(exc) in {
            "Official source returned no real notices",
            "Worker did not persist all authentic records",
            "Real Worker SQL persistence mismatch",
            "Official source identity mismatch",
            "Actual public FastAPI endpoint unavailable",
            "Guest search returned no legitimate locked results",
            "No safe visible titles in original real notices",
            "Guest API contains a non-worker/fabricated notice",
            "Guest API exposed protected details",
            "No matching search term in real visible notice titles",
            "Keyword from authentic notice failed public HTTP search",
            "Public real search is cacheable",
            "Guest could open a protected tender detail route",
            "Unrelated query returned invented/nonmatching results",
            "No genuine title term for scoped company test",
            "Real API company registration failed",
            "Authenticated snapshot Discovery API failed",
            "Real worker source produced no authenticated matches",
            "Discovery returned a non-worker notice",
            "Unverified AI analysis was claimed",
            "Cross-tenant registered user could access search",
            "Authorized real-notice shortlist save failed",
            "Saved notice identity changed",
            "Real saved notice did not persist in account shortlist",
            "Real saved opportunity is not duplicate-idempotent",
            "Cross-tenant registered user could read saved genuine tenders",
        }:
            print("FAILURE_DETAIL="+str(exc))
        print("PRODUCTION_CHANGED=NO")
        raise SystemExit(2)
    print("RU_REAL_GUEST_API_EVIDENCE="+json.dumps(evidence,sort_keys=True))
    print("RU_REAL_GUEST_API=PASS_REAL_GUEST_AND_AUTHENTICATED_SNAPSHOT_ONLY")
    print("PRODUCTION_CHANGED=NO")
