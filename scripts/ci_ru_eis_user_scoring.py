"""Strict Windows-host real EIS 44/223 -> DB -> signed-in scoring acceptance.

This is a *host-only acceptance test*, not a background production connector.
Actual public EIS RSS responses are required; no notice fixture or mock network
is permitted. Only synthetic user/company accounts and an ephemeral SQLite
database are created. Certificate trust is scoped to this process and checked
against the immutable official DER SHA-256 pin.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
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
from app.organizations import OrganizationService
from app.scoring.preview import score_metadata_preview
from app.services.tender_analysis import analysis_from_notice
from app.sources.catalog import build_source_catalog
from app.sources.snapshots import snapshot_catalog
from scripts.ru_eis_pinned_tls_probe import official_download, verify_root
from scripts.ru_public_live_smoke import _settings
from test_scoring_workers import system as synthetic_system, run as run_job

EIS_KEYS = ("eis", "eis_223")
LIMIT_PER_SOURCE = 10


def matching_keyword(title: str) -> str:
    """Select a real, non-empty word from the actual public tender title."""
    words = re.findall(r"[\w-]{4,}", title, flags=re.UNICODE)
    if not words:
        raise ValueError("No usable real procurement keyword")
    return words[0][:100]


async def fetch_public_notices(catalog, key):
    adapter = catalog.registry.get(key).source
    return await asyncio.wait_for(adapter.fetch(limit=LIMIT_PER_SOURCE), timeout=35)


async def exact_local_lookup(catalog, repository, key, notice):
    result = await snapshot_catalog(catalog, repository).fetch(
        source_keys=(key,), search_terms=(notice.external_id,),
        limit_per_source=LIMIT_PER_SOURCE,
    )
    return not result.failures and any(
        found.identity == notice.identity and found.url == notice.url
        for found in result.notices
    )


def score_under_synthetic_login(state, catalog, key, keyword):
    # Preserve runtime HTTP permissions, actual scoring worker and public
    # source revision checks. None of these calls contact external AI services.
    profile = state.profile.model_copy(update={
        "product_keywords": [keyword],
        "search_keywords": [keyword],
        "excluded_keywords": [],
        "accepted_currencies": ["RUB"],
        "min_contract_value": None,
        "max_contract_value": None,
        "hard_stop_on_currency": False,
    })
    state.companies.update_for_organization(
        account_id=state.accounts[0].id,
        organization_id=state.org.id,
        company_id=state.company.id,
        profile=profile,
    )
    state.service.catalog = catalog
    runtime = ApiRuntime(
        auth_service=state.auth,
        scoring_run_service=state.service,
        source_catalog=catalog,
        company_service=CompanyService(state.companies),
        organization_service=OrganizationService(state.orgs),
    )
    app = create_app(runtime=runtime, settings=ApiSettings(
        host="127.0.0.1", port=8000, reload=False, api_key="synthetic-eis-e2e",
    ))
    route = (f"/api/v1/organizations/{state.org.id}/companies/"
             f"{state.company.id}/scoring/runs")
    with TestClient(app) as client:
        if client.post(route, json={"sources": [key]}).status_code != 401:
            raise AssertionError("Unauthenticated EIS scoring was allowed")
        client.cookies.set(SESSION_COOKIE, state.auth.create_session(state.accounts[0]))
        created = client.post(route, json={
            "sources": [key], "limit_per_source": LIMIT_PER_SOURCE,
        })
        if created.status_code != 202:
            raise AssertionError("Authorized EIS scoring rejected")
        job_id = created.json()["job_id"]
        steps = 0
        while run_job(state):
            steps += 1
            if steps > 5:
                raise AssertionError("Worker execution bound exceeded")
        completed = client.get(route + "/" + job_id)
        if completed.status_code != 200:
            raise AssertionError("Authenticated result lookup failed")
        body = completed.json()
        if (not body.get("complete") or body.get("candidate_count", 0) < 1
                or body.get("result_count", 0) < 1
                or not body.get("items")
                or any(item.get("source_id") != key for item in body["items"])
                or not all("criteria" in item.get("scoring", {})
                           for item in body["items"])):
            raise AssertionError("No verified real EIS scoring result")
        revisions = client.get(route + "/" + job_id + "/revisions")
        if revisions.status_code != 200:
            raise AssertionError("EIS source revisions could not be queried")
        client.cookies.set(SESSION_COOKIE, state.auth.create_session(state.accounts[4]))
        if client.get(route + "/" + job_id).status_code != 403:
            raise AssertionError("Cross-tenant scoring access was accepted")
    return body["result_count"]


def strict_acceptance(root_der_or_pem: bytes):
    pem = verify_root(root_der_or_pem)
    # Pin verified before any attempt to contact an EIS source.
    with tempfile.TemporaryDirectory(prefix="valyqon-eis-auth-") as temporary:
        cert_file = Path(temporary) / "isolated-eis-root.pem"
        cert_file.write_text(pem, encoding="ascii", newline="\n")
        previous = os.environ.get("VALYQON_RU_EIS_CA_CERT")
        try:
            os.environ["VALYQON_RU_EIS_CA_CERT"] = str(cert_file)
            catalog = build_source_catalog(_settings())
            if not all(key in catalog.enabled_keys for key in EIS_KEYS):
                raise AssertionError("A required EIS source is not explicitly enabled")
            captures = {}
            for key in EIS_KEYS:
                notices = asyncio.run(fetch_public_notices(catalog, key))
                if not 1 <= len(notices) <= LIMIT_PER_SOURCE:
                    raise AssertionError("No real EIS notices")
                if any(n.source != key or not n.external_id or not n.url for n in notices):
                    raise AssertionError("Invalid EIS notice identity")
                captures[key] = notices

            fixture = synthetic_system.__wrapped__(Path(temporary))
            state = next(fixture)
            try:
                for key in EIS_KEYS:
                    notices = captures[key]
                    for notice in notices:
                        state.store.upsert(notice, f"connector-sync-v1:{key}:adapter-r1")
                    matches = sum(bool(asyncio.run(exact_local_lookup(
                        catalog, state.store, key, notice))) for notice in notices)
                    if matches != len(notices):
                        raise AssertionError("EIS source-to-DB-query proof incomplete")

                    scored = score_under_synthetic_login(
                        state, catalog, key, matching_keyword(notices[0].title),
                    )
                    profile = state.companies.get_for_organization(
                        account_id=state.accounts[0].id,
                        organization_id=state.org.id,
                        company_id=state.company.id,
                    )
                    # The public metadata-based preview is deterministic.
                    evaluation = score_metadata_preview(
                        analysis_from_notice(notices[0]), profile.profile
                    )
                    if len(evaluation.criteria) != 6:
                        raise AssertionError("Deterministic EIS criteria unavailable")
                    print("EIS_AUTH_SOURCE=" + key + "; RECEIVED=" + str(len(notices))
                          + "; DB_QUERY=" + str(matches)
                          + "; AUTH_SCORING=" + str(scored), flush=True)
                return True
            finally:
                try:
                    next(fixture)
                except StopIteration:
                    pass
        finally:
            if previous is None:
                os.environ.pop("VALYQON_RU_EIS_CA_CERT", None)
            else:
                os.environ["VALYQON_RU_EIS_CA_CERT"] = previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-cer", type=Path, default=None,
                        help="Optional original official Russian root CA certificate")
    args = parser.parse_args()
    stage = "certificate"
    try:
        certificate = args.root_cer.read_bytes() if args.root_cer else official_download()
        stage = "public_fetch_and_scoring"
        result = strict_acceptance(certificate)
        if not result:
            raise AssertionError("No evidence")
    except Exception as error:
        # Only fixed stage and exception class; never print notice text, URL,
        # account/session data, certificate bytes or arbitrary exception details.
        print("EIS_REAL_AUTH_SCORING=BLOCKED", flush=True)
        print("FAILURE_STAGE=" + stage, flush=True)
        print("FAILURE_CLASS=" + type(error).__name__, flush=True)
        print("SYSTEM_TRUST_CHANGED=NO; PRODUCTION_CHANGED=NO", flush=True)
        return 1
    print("EIS_REAL_AUTH_SCORING=PASS", flush=True)
    print("EXTERNAL_GENERATIVE_LLM_VERIFIED=NO", flush=True)
    print("NOTICE_DETAIL_VERIFIED=NO", flush=True)
    print("SYSTEM_TRUST_CHANGED=NO; PRODUCTION_CHANGED=NO", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
