"""Real Samara public LIST records -> SQLite -> authenticated customer scoring proof.

Only original government list rows are real; individual detail pages remain unverified. All accounts and databases are synthetic.
No remote LLM, deployment, production credentials, or persistent data writes.
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
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import connector_version
from app.sources.snapshots import snapshot_catalog
from test_scoring_workers import system as synthetic_system, run as run_job

SOURCE = "ru_samara_public_list"


def acceptance():
    catalog = build_source_catalog(MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=3,
        max_notifications_per_cycle=5, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        ru_samara_public_list_enabled=True,
    ))
    if SOURCE not in catalog.enabled_keys:
        raise AssertionError("SAMARA public catalog not explicitly enabled")
    # Public-list-only; no independently verified original detail GETs.
    notices = asyncio.run(catalog.registry.get(SOURCE).source.fetch(limit=3))
    if not 1 <= len(notices) <= 3:
        raise AssertionError("No real independently verified SAMARA tender data")

    with tempfile.TemporaryDirectory(prefix="valyqon-samara-auth-real-") as directory:
        fixture = synthetic_system.__wrapped__(Path(directory))
        state = next(fixture)
        try:
            state.service.catalog = catalog
            found = 0
            for notice in notices:
                state.store.upsert(notice, connector_version(SOURCE))
                result = asyncio.run(snapshot_catalog(catalog, state.store).fetch(
                    source_keys=(SOURCE,),
                    search_terms=(notice.external_id,),
                    limit_per_source=10,
                ))
                if result.failures or not any(
                    row.identity == notice.identity and row.url == notice.url
                    for row in result.notices
                ):
                    raise AssertionError("Real SAMARA notice not searchable from SQL")
                found += 1

            keyword = next((word for word in notices[0].title.split()
                            if len(word) >= 4), notices[0].title[:20])
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
                auth_service=state.auth,
                scoring_run_service=state.service,
                source_catalog=catalog,
                company_service=CompanyService(state.companies),
                organization_service=OrganizationService(state.orgs),
            )
            api = create_app(runtime=runtime, settings=ApiSettings(
                host="127.0.0.1", port=8000, reload=False, api_key="synthetic",
            ))
            url = (f"/api/v1/organizations/{state.org.id}/companies/"
                   f"{state.company.id}/scoring/runs")
            with TestClient(api) as client:
                if client.post(url, json={"sources": [SOURCE]}).status_code != 401:
                    raise AssertionError("Unauthenticated SAMARA scoring accepted")
                client.cookies.set(SESSION_COOKIE, state.auth.create_session(state.accounts[0]))
                created = client.post(url, json={"sources": [SOURCE], "limit_per_source": 3})
                if created.status_code != 202:
                    raise AssertionError("Authorized SAMARA scoring request rejected")
                job_id = created.json()["job_id"]
                runs = 0
                while run_job(state):
                    runs += 1
                    if runs > 5:
                        raise AssertionError("Unbounded scoring jobs")
                response = client.get(url + "/" + job_id)
                if response.status_code != 200:
                    raise AssertionError("SAMARA scoring result inaccessible")
                body = response.json()
                if (not body.get("complete") or body.get("result_count", 0) < 1
                        or body.get("candidate_count", 0) < 1
                        or not any("criteria" in item.get("scoring", {})
                                   and item.get("source_id") == SOURCE
                                   for item in body.get("items", []))):
                    raise AssertionError("Real SAMARA tender did not reach customer scoring")
                if client.get(url + "/" + job_id + "/revisions").status_code != 200:
                    raise AssertionError("SAMARA scored source revisions unavailable")
                client.cookies.set(SESSION_COOKIE, state.auth.create_session(state.accounts[4]))
                if client.get(url + "/" + job_id).status_code != 403:
                    raise AssertionError("Cross-tenant scoring disclosure")
                return {
                    "real_public_list_rows": len(notices),
                    "sql_keyword_roundtrips": found,
                    "authenticated_scoring_results": body["result_count"],
                    "cross_tenant_denied": True,
                    "external_ai_used": False,
                    "production_changed": False,
                }
        finally:
            try:
                next(fixture)
            except StopIteration:
                pass


def main():
    try:
        evidence = acceptance()
    except Exception as exc:
        print("RU_SAMARA_REAL_AUTH=BLOCKED")
        print("FAILURE_CLASS=" + type(exc).__name__)
        # Only reveal fixed static local assertion categories, never arbitrary
        # exception text, credentials, user data, supplier details or tokens.
        known = {
            "SAMARA public catalog not explicitly enabled": "CATALOG_NOT_ENABLED",
            "No real independently verified SAMARA tender data": "EMPTY_REAL_PUBLIC_LIST",
            "Real SAMARA notice not searchable from SQL": "SQL_SOURCE_SEARCH",
            "Unauthenticated SAMARA scoring accepted": "UNAUTHENTICATED_REQUEST",
            "Authorized SAMARA scoring request rejected": "AUTHORIZED_POST",
            "Unbounded scoring jobs": "UNBOUNDED_WORKER",
            "SAMARA scoring result inaccessible": "AUTHORIZED_RESULT",
            "Real SAMARA tender did not reach customer scoring": "SCORING_RESULT",
            "SAMARA scored source revisions unavailable": "REVISIONS",
            "Cross-tenant scoring disclosure": "TENANT_ISOLATION",
        }
        gate = known.get(str(exc), "UNCLASSIFIED") if type(exc) is AssertionError else "NON_ASSERTION"
        print("FAILURE_GATE=" + gate)
        print("PRODUCTION_CHANGED=NO")
        return 1
    print("RU_SAMARA_REAL_AUTH_EVIDENCE=" + json.dumps(evidence, sort_keys=True))
    print("RU_SAMARA_REAL_AUTH=PASS")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
