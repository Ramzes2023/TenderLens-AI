"""Strict, real-network B2B-Center -> ephemeral DB -> authenticated scoring acceptance.

No fixtures for procurement data; all customer accounts/profiles are synthetic.
No production environment, external credentials, TLS bypass or AI-provider claim.
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
from app.organizations import OrganizationService
from app.scoring.preview import score_metadata_preview
from app.services.tender_analysis import analysis_from_notice
from app.sources.catalog import build_source_catalog
from app.sources.snapshots import snapshot_catalog
from scripts.ru_public_live_smoke import _settings
from test_scoring_workers import system as synthetic_system, run as run_job

SOURCE = "b2b_center"
VERSION = "connector-sync-v1:b2b_center:adapter-r1"


async def public_notices(catalog):
    from unittest.mock import patch
    from app.sources import b2b_center
    from app.sources.b2b_center import _Document, _Node
    source = catalog.registry.get(SOURCE).source
    original = b2b_center.parse_b2b_center_listing
    safe_original = b2b_center._safe_url

    def measured_safe_url(raw, *, detail=False):
        try:
            return safe_original(raw, detail=detail)
        except Exception:
            from urllib.parse import urljoin, urlsplit
            from re import fullmatch
            try:
                p = urlsplit(urljoin(b2b_center.B2B_CENTER_LIST_URL, raw or ""))
                data = {"detail": bool(detail), "scheme": p.scheme,
                        "host": p.hostname, "query_present": bool(p.query),
                        "fragment_present": bool(p.fragment),
                        "path_matches_expected": bool(fullmatch(
                            r"/search/number/[A-Za-z0-9-]{1,100}/", p.path))}
                print("B2B_UNSAFE_URL_SHAPE=" + repr(data), flush=True)
            except Exception:
                print("B2B_UNSAFE_URL_SHAPE=UNPARSEABLE", flush=True)
            raise

    def observed_parse(payload, *, limit=100, listing_url=b2b_center.B2B_CENTER_LIST_URL):
        # Structural counts only; no raw HTML, tender identifiers or content.
        doc = _Document()
        doc.feed(payload.decode("utf-8-sig"))
        doc.close()
        profiles = []
        for node in doc.root.walk():
            if (node.tag == "div" and "cards" in (node.attrs.get("class") or "").split()
                and node.attrs.get("itemtype") == "https://schema.org/ListItem"):
                children = list(node.walk())
                org = sum(c.attrs.get("itemtype") == "https://schema.org/Organization"
                          for c in children)
                demand = sum(c.attrs.get("itemtype") == "https://schema.org/Demand"
                             for c in children)
                profiles.append((org, demand))
        print("B2B_LIVE_CARD_SHAPES=" + str(profiles[:12]), flush=True)
        print("B2B_TOTAL_LISTITEM_CARDS=" + str(len(profiles)), flush=True)
        from urllib.parse import urljoin, urlsplit
        hosts = {}
        for card in doc.root.walk():
            if (card.tag == "div" and "cards" in (card.attrs.get("class") or "").split()
                and card.attrs.get("itemtype") == "https://schema.org/ListItem"):
                for demand in card.walk():
                    if demand.attrs.get("itemtype") == "https://schema.org/Demand":
                        raw = b2b_center._property(demand, "url", "link")
                        if raw:
                            host = urlsplit(urljoin(b2b_center.B2B_CENTER_LIST_URL, raw)).hostname
                            hosts[host or "(missing)"] = hosts.get(host or "(missing)", 0) + 1
        print("B2B_LIVE_CARD_HOST_COUNTS=" + repr(hosts), flush=True)
        try:
            records = original(payload, limit=limit, listing_url=listing_url)
            print("B2B_REAL_NORMALIZED_CARD_COUNT=" + str(len(records)), flush=True)
            return records
        except Exception as error:
            print("B2B_REAL_PARSER_ERROR_CLASS=" + type(error).__name__, flush=True)
            raise

    with patch.object(b2b_center, "_safe_url", measured_safe_url), \
            patch.object(b2b_center, "parse_b2b_center_listing", observed_parse):
        return await asyncio.wait_for(source.fetch(limit=10), timeout=30)


async def keyword_roundtrip(catalog, repository, notice):
    from app.sources.opportunities import validate_notice
    validate_notice(notice, SOURCE)
    report = await snapshot_catalog(catalog, repository).fetch(
        source_keys=(SOURCE,), search_terms=(notice.external_id,), limit_per_source=10,
    )
    return not report.failures and any(
        item.identity == notice.identity and item.url == notice.url for item in report.notices
    )


def acceptance():
    # No .env is loaded; the existing production fetcher uses its exact-host,
    # bounded request transport with strict TLS and no cookies or redirects.
    settings = _settings()
    catalog = build_source_catalog(settings)
    if SOURCE not in catalog.enabled_keys:
        raise AssertionError("B2B-Center was not enabled in the isolated catalog")
    notices = asyncio.run(public_notices(catalog))
    print("B2B_REAL_FETCHED_COUNT=" + str(len(notices)), flush=True)
    if not notices or len(notices) > 10:
        raise AssertionError("No live B2B procurement notices")
    if any(item.source != SOURCE or not item.external_id or not item.url for item in notices):
        raise AssertionError("Malformed B2B live data")

    with tempfile.TemporaryDirectory(prefix="valyqon-b2b-auth-live-") as directory:
        # Reuse the actual production repositories, security and job worker.
        # The existing test fixture builds synthetic users in the temp database.
        fixture = synthetic_system.__wrapped__(Path(directory))
        state = next(fixture)
        try:
            state.service.catalog = catalog
            matched = 0
            for notice in notices:
                state.store.upsert(notice, VERSION)
                if asyncio.run(keyword_roundtrip(catalog, state.store, notice)):
                    matched += 1
            if matched != len(notices):
                raise AssertionError("Public notice DB-to-query identity mismatch")

            # A scoped synthetic customer can match an actual, unmodified notice.
            # No source text is printed or sent to external AI providers.
            key = next((word for word in notices[0].title.split()
                        if len(word) >= 3), notices[0].title[:25])
            profile = state.profile.model_copy(update={
                "product_keywords": [key],
                "monitoring_keywords": [],
                "accepted_currencies": ["RUB"],
                "max_contract_value": 100000000000.0,
            })
            state.companies.update_for_organization(
                account_id=state.accounts[0].id, organization_id=state.org.id,
                company_id=state.company.id, profile=profile,
            )
            state.profile = profile
            state.store.initialize()
            runtime = ApiRuntime(
                auth_service=state.auth, scoring_run_service=state.service,
                source_catalog=catalog,
                company_service=CompanyService(state.companies),
                organization_service=OrganizationService(state.orgs),
            )
            api = create_app(
                runtime=runtime,
                settings=ApiSettings(host="127.0.0.1", port=8000, reload=False, api_key="synthetic"),
            )
            url = (f"/api/v1/organizations/{state.org.id}/companies/"
                   f"{state.company.id}/scoring/runs")
            with TestClient(api) as client:
                if client.post(url, json={"sources": [SOURCE]}).status_code != 401:
                    raise AssertionError("Unauthenticated scoring not rejected")
                client.cookies.set(SESSION_COOKIE, state.auth.create_session(state.accounts[0]))
                created = client.post(url, json={"sources": [SOURCE], "limit_per_source": 10})
                if created.status_code != 202:
                    raise AssertionError("Authenticated scoring was not accepted")
                job_id = created.json()["job_id"]
                executions = 0
                while run_job(state):
                    executions += 1
                    if executions > 5:
                        raise AssertionError("Bounded worker execution exceeded")
                result = client.get(url + "/" + job_id)
                if result.status_code != 200:
                    raise AssertionError("Authorized scoring result not available")
                body = result.json()
                if (not body.get("complete") or body.get("result_count", 0) < 1 or
                    body.get("candidate_count", 0) < 1 or
                    any(item.get("source_id") != SOURCE for item in body.get("items", [])) or
                    not any("criteria" in item.get("scoring", {}) for item in body["items"])):
                    raise AssertionError("Real public B2B notice was not scored")
                page = client.get(url + "/" + job_id + "/revisions")
                if page.status_code != 200:
                    raise AssertionError("Scored source revision details unavailable")
                client.cookies.set(
                    SESSION_COOKIE, state.auth.create_session(state.accounts[4])
                )
                if client.get(url + "/" + job_id).status_code != 403:
                    raise AssertionError("Cross-tenant access was not denied")
                offline_analysis = score_metadata_preview(
                    analysis_from_notice(notices[0]), profile
                )
                if len(offline_analysis.criteria) != 6:
                    raise AssertionError("Deterministic notice analysis missing criteria")
                return {"real_notice_count": len(notices),
                        "db_search_verified": matched,
                        "authorized_score_results": body["result_count"],
                        "tenant_isolation": True,
                        "llm_provider_used": False,
                        "notice_details_independently_verified": False}
        finally:
            try:
                next(fixture)
            except StopIteration:
                pass


def main():
    try:
        evidence = acceptance()
    except Exception as error:
        # Only allow fixed, source-code-controlled SourceError reason strings.
        # Never print arbitrary exceptions, customer data, URLs or response bodies.
        from app.sources.eis_rss import SourceError
        print("RU_B2B_REAL_AUTH_SCORING=BLOCKED")
        print("FAILURE_CLASS=" + type(error).__name__)
        if isinstance(error, SourceError):
            known = {"B2B-Center returned no usable procurement records.",
                     "B2B-Center unexpected procurement card structure.",
                     "B2B-Center empty or oversized HTML.",
                     "B2B-Center listing unavailable.",
                     "B2B-Center returned unsafe notice URL.",
                     "B2B-Center procurement title missing.",
                     "B2B-Center conflicting structured properties."}
            print("SOURCE_BLOCKER=" + (str(error) if str(error) in known
                                      else "OTHER_SOURCE_ERROR"))
        return 1
    print("RU_B2B_REAL_AUTH_SCORING=PASS")
    print("RU_B2B_EVIDENCE=" + json.dumps(evidence, sort_keys=True))
    print("PRIVATE_OR_PRODUCTION_DB_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
