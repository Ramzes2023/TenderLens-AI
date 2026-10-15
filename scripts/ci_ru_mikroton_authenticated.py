"""Strict live MikroTon -> ephemeral SQLite -> authenticated customer scoring proof.

Real public procurement data cannot be mocked. Only customer accounts and the
database are synthetic. This never loads production secrets or enables sync.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.security import SESSION_COOKIE
from app.companies import CompanyService
from app.monitoring.config import MonitoringSettings
from app.organizations import OrganizationService
from app.scoring.preview import score_metadata_preview
from app.services.tender_analysis import analysis_from_notice
from app.sources.catalog import build_source_catalog
from app.sources.opportunities import validate_notice
from app.sources.snapshots import snapshot_catalog
from scripts.ci_ru_mikroton_real_api import acceptance as live_api_proof
from test_scoring_workers import system as synthetic_system, run as run_job

SOURCE = "mikroton_tender"
VERSION = "connector-sync-v1:mikroton_tender:adapter-r1"


def isolated_catalog():
    settings = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=10,
        max_notifications_per_cycle=5, request_timeout=15.0,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        mikroton_tender_enabled=True,
    )
    return build_source_catalog(settings)


async def exact_db_keyword(catalog, store, notice):
    result = await snapshot_catalog(catalog, store).fetch(
        source_keys=(SOURCE,), search_terms=(notice.external_id,),
        limit_per_source=10,
    )
    return not result.failures and any(
        row.identity == notice.identity and row.url == notice.url
        for row in result.notices
    )


def integration():
    proof = asyncio.run(live_api_proof())
    if not (proof["listing_200"] == 2 and proof["real_notice_count"] > 0
            and proof["detail_http_200"] and proof["detail_identity_verified"]):
        raise AssertionError("Real independent source API proof unavailable")

    catalog = isolated_catalog()
    if SOURCE not in catalog.enabled_keys:
        raise AssertionError("Source not enabled in isolated catalog")
    notices = asyncio.run(catalog.registry.get(SOURCE).source.fetch(limit=10))
    if not notices or len(notices) > 10:
        raise AssertionError("No real normalized procurement notices")
    for notice in notices:
        validate_notice(notice, SOURCE)

    with tempfile.TemporaryDirectory(prefix="valyqon-ru-mikroton-auth-") as directory:
        fixture = synthetic_system.__wrapped__(Path(directory))
        state = next(fixture)
        try:
            state.service.catalog = catalog
            found = 0
            for notice in notices:
                state.store.upsert(notice, VERSION)
                found += int(asyncio.run(exact_db_keyword(catalog, state.store, notice)))
            if found != len(notices):
                raise AssertionError("Actual source-to-DB and search roundtrip failed")

            keyword = next((s for s in notices[0].title.split()
                            if len(s) >= 3), notices[0].title[:20])
            profile = state.profile.model_copy(update={
                "product_keywords": [keyword],
                "monitoring_keywords": [],
                "accepted_currencies": ["RUB"],
                "max_contract_value": 100000000000.0,
            })
            state.companies.update_for_organization(
                account_id=state.accounts[0].id, organization_id=state.org.id,
                company_id=state.company.id, profile=profile,
            )
            state.profile = profile

            runtime = ApiRuntime(
                auth_service=state.auth, scoring_run_service=state.service,
                source_catalog=catalog,
                company_service=CompanyService(state.companies),
                organization_service=OrganizationService(state.orgs),
            )
            app = create_app(runtime=runtime, settings=ApiSettings(
                host="127.0.0.1", port=8000, reload=False, api_key="synthetic",
            ))
            url = (f"/api/v1/organizations/{state.org.id}/companies/"
                   f"{state.company.id}/scoring/runs")
            with TestClient(app) as client:
                if client.post(url, json={"sources": [SOURCE]}).status_code != 401:
                    raise AssertionError("Unauthenticated access unexpectedly accepted")
                client.cookies.set(SESSION_COOKIE, state.auth.create_session(state.accounts[0]))
                submitted = client.post(url, json={
                    "sources": [SOURCE], "limit_per_source": 10,
                })
                if submitted.status_code != 202:
                    raise AssertionError("Authorized scoring submission failed")
                job_id = submitted.json()["job_id"]
                n = 0
                while run_job(state):
                    n += 1
                    if n > 5:
                        raise AssertionError("Unexpected unbounded worker execution")
                result = client.get(url + "/" + job_id)
                if result.status_code != 200:
                    raise AssertionError("Scoring result unavailable to original user")
                body = result.json()
                if (not body.get("complete") or body.get("result_count", 0) < 1
                        or body.get("candidate_count", 0) < 1
                        or not body.get("items")
                        or any(row.get("source_id") != SOURCE for row in body["items"])
                        or not any("criteria" in row.get("scoring", {})
                                   for row in body["items"])):
                    raise AssertionError("No actual source notice was scored")
                if client.get(url + "/" + job_id + "/revisions").status_code != 200:
                    raise AssertionError("Source revisions not available")
                client.cookies.set(SESSION_COOKIE, state.auth.create_session(state.accounts[4]))
                if client.get(url + "/" + job_id).status_code != 403:
                    raise AssertionError("Cross-tenant data exposure")
            score = score_metadata_preview(analysis_from_notice(notices[0]), profile)
            if len(score.criteria) != 6:
                raise AssertionError("Missing metadata based scoring criteria")
            return {
                "real_api_notice_count": proof["real_notice_count"],
                "real_public_detail_verified": True,
                "stored_search_identity_count": found,
                "authenticated_score_count": body["result_count"],
                "tenant_isolation": True,
                "generative_llm_verified": False,
                "production_changed": False,
            }
        finally:
            try:
                next(fixture)
            except StopIteration:
                pass


def main():
    try:
        evidence = integration()
    except Exception as error:
        # Fixed failure class only, no customer, source, secret, HTTP body or URL.
        print("RU_MIKROTON_REAL_AUTH=BLOCKED", flush=True)
        print("FAILURE_CLASS=" + type(error).__name__, flush=True)
        print("PRODUCTION_CHANGED=NO", flush=True)
        return 1
    print("RU_MIKROTON_REAL_AUTH_EVIDENCE=" +
          json.dumps(evidence, sort_keys=True), flush=True)
    print("RU_MIKROTON_REAL_AUTH=PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
