import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.security import SESSION_COOKIE
from app.auth import AuthRepository, AuthService
from app.companies import CompanyRepository, CompanyService
from app.monitoring import (
    MonitoringRepository,
    MonitoringSettings,
    TenderMonitorService,
)
from app.organizations import (
    OrganizationRepository,
    OrganizationService,
    Role,
)
from app.sources.models import TenderNotice
from app.sources.multi import MultiSourceFetchReport


class DynamicSource:
    def __init__(self, notices, terms=()):
        self.notices = notices
        self.terms = tuple(terms)

    def for_search_terms(
        self,
        search_terms,
        *,
        max_feeds=5,
    ):
        return DynamicSource(
            self.notices,
            tuple(search_terms)[:max_feeds],
        )

    async def fetch(self, limit=20):
        return self.notices[:limit]


class FakeCatalog:
    def __init__(self, notices):
        self.notices = tuple(notices)
        self.calls = []

    async def fetch(
        self,
        *,
        limit_per_source=20,
        source_keys=None,
        search_terms=(),
        max_eis_feeds=5,
    ):
        self.calls.append(
            {
                "limit_per_source":
                    limit_per_source,
                "source_keys":
                    source_keys,
                "search_terms":
                    tuple(search_terms),
                "max_eis_feeds":
                    max_eis_feeds,
            }
        )

        return MultiSourceFetchReport(
            notices=self.notices[
                : limit_per_source * 2
            ],
            failures=(),
            attempted_sources=(
                "ted",
                "uk_fts",
            ),
            successful_sources=(
                "ted",
                "uk_fts",
            ),
            statuses=(),
        )


class OrganizationWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.path = (
            Path(self.temp.name)
            / "organization-workflows.db"
        )

        auth_repository = AuthRepository(self.path)
        auth_repository.initialize()

        organization_repository = OrganizationRepository(
            self.path
        )
        organization_repository.initialize()

        company_repository = CompanyRepository(
            self.path
        )
        company_repository.initialize()

        monitoring_repository = MonitoringRepository(
            self.path
        )
        monitoring_repository.initialize()
        self.monitoring_repository = monitoring_repository

        self.auth = AuthService(
            auth_repository
        )
        self.organizations = OrganizationService(
            organization_repository
        )
        self.companies = CompanyService(
            company_repository
        )

        self.owner = self.auth.register(
            "workflow-owner@example.com",
            "very secure password 123",
        )
        self.member = self.auth.register(
            "workflow-member@example.com",
            "very secure password 123",
        )
        self.viewer = self.auth.register(
            "workflow-viewer@example.com",
            "very secure password 123",
        )
        self.outsider = self.auth.register(
            "workflow-outsider@example.com",
            "very secure password 123",
        )

        self.organization = organization_repository.create(
            "Workflow Organization",
            self.owner.id,
        )

        organization_repository.add_membership(
            self.organization.id,
            self.member.id,
            Role.MEMBER,
        )
        organization_repository.add_membership(
            self.organization.id,
            self.viewer.id,
            Role.VIEWER,
        )

        notice = TenderNotice(
            source="eis",
            external_id="shared-notice-1",
            title="Supply of aluminium profile",
            url="https://example.test/tender/1",
            initial_price=1_000_000,
            currency="RUB",
        )

        monitoring_settings = MonitoringSettings(
            enabled=False,
            interval_seconds=600,
            max_items=20,
            max_notifications_per_cycle=5,
            request_timeout=30.0,
            eis_rss_urls=(
                "https://example.test/static-rss",
            ),
            ca_bundle_file=None,
            profile_feeds_enabled=True,
            profile_feed_limit=5,
        )

        self.monitoring = TenderMonitorService(
            monitoring_settings,
            DynamicSource([notice]),
            monitoring_repository,
            None,
        )

        self.catalog = FakeCatalog(
            [
                TenderNotice(
                    source="ted",
                    external_id="global-aluminium-1",
                    title="Supply of aluminium profile",
                    url="https://example.test/ted/1",
                    initial_price=2_000_000,
                    currency="EUR",
                ),
                TenderNotice(
                    source="uk_fts",
                    external_id="global-copper-1",
                    title="Supply of copper cable",
                    url="https://example.test/uk/1",
                    initial_price=500_000,
                    currency="GBP",
                ),
            ]
        )

        runtime = ApiRuntime(
            auth_service=self.auth,
            organization_service=self.organizations,
            company_service=self.companies,
            monitoring_service=self.monitoring,
            tender_discovery_service=self.monitoring,
            source_catalog=self.catalog,
        )

        settings = ApiSettings(
            host="127.0.0.1",
            port=8000,
            reload=False,
            api_key="legacy-secret",
        )

        self.context = TestClient(
            create_app(
                runtime=runtime,
                settings=settings,
            )
        )
        self.client = self.context.__enter__()

        self.addCleanup(
            self.context.__exit__,
            None,
            None,
            None,
        )

    def as_account(self, account):
        self.client.cookies.clear()

        token = self.auth.create_session(account)

        self.client.cookies.set(
            SESSION_COOKIE,
            token,
        )

    def base(self, suffix):
        return (
            f"/api/v1/organizations/"
            f"{self.organization.id}"
            f"{suffix}"
        )

    @staticmethod
    def profile(
        name,
        keyword="aluminium",
    ):
        return {
            "profile_version":
                "organization-workflow-test",
            "company_name": name,
            "business_mode": "sell",
            "product_keywords": [keyword],
            "search_keywords": [keyword],
            "accepted_currencies": ["RUB"],
        }

    @staticmethod
    def analysis():
        return {
            "title": "Supply of aluminium profile",
            "initial_price": 1_000_000,
            "currency": "RUB",
            "procurement_object":
                "aluminium profile",
        }

    def create_company(
        self,
        name,
        keyword="aluminium",
    ):
        response = self.client.post(
            self.base("/companies"),
            json={
                "name": name,
                "profile": self.profile(
                    name,
                    keyword,
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            201,
            response.text,
        )

        return response.json()

    def test_scoring_uses_shared_active_company(self):
        self.as_account(self.owner)

        first = self.create_company(
            "Shared Aluminium",
            "aluminium",
        )

        second = self.create_company(
            "Shared Cable",
            "cable",
        )

        self.assertTrue(
            first["is_active"]
        )
        self.assertFalse(
            second["is_active"]
        )

        self.as_account(self.member)

        scored = self.client.post(
            self.base("/scoring/evaluate"),
            json=self.analysis(),
        )

        self.assertEqual(
            scored.status_code,
            200,
            scored.text,
        )
        self.assertEqual(
            scored.json()["profile_name"],
            "Shared Aluminium",
        )

        switched = self.client.post(
            self.base(
                f"/companies/{second['id']}/activate"
            )
        )
        self.assertEqual(
            switched.status_code,
            200,
            switched.text,
        )

        self.as_account(self.owner)

        rescored = self.client.post(
            self.base("/scoring/evaluate"),
            json=self.analysis(),
        )

        self.assertEqual(
            rescored.status_code,
            200,
            rescored.text,
        )
        self.assertEqual(
            rescored.json()["profile_name"],
            "Shared Cable",
        )

        self.as_account(self.viewer)

        viewer_score = self.client.post(
            self.base("/scoring/evaluate"),
            json=self.analysis(),
        )

        self.assertEqual(
            viewer_score.status_code,
            200,
            viewer_score.text,
        )

    def test_global_discovery_uses_catalog_and_active_company(self):
        self.as_account(
            self.owner
        )

        self.create_company(
            "Discover Aluminium",
            "aluminium",
        )

        self.as_account(
            self.viewer
        )

        first = self.client.post(
            self.base(
                "/discover/tenders"
            )
        )

        self.assertEqual(
            first.status_code,
            200,
            first.text,
        )

        payload = first.json()

        self.assertEqual(
            len(payload["items"]),
            1,
        )

        self.assertEqual(
            payload["items"][0]["source"],
            "ted",
        )

        self.assertEqual(
            payload["items"][0]["external_id"],
            "global-aluminium-1",
        )

        item = payload["items"][0]

        self.assertEqual(
            item["analysis_stage"],
            "metadata_preview",
        )

        self.assertFalse(
            item["full_ai_analyzed"]
        )

        self.assertEqual(
            item["metadata_analysis"]["title"],
            "Supply of aluminium profile",
        )

        self.assertEqual(
            item["metadata_analysis"]["initial_price"],
            2_000_000,
        )

        self.assertEqual(
            item["metadata_analysis"]["currency"],
            "EUR",
        )

        self.assertIsNone(
            item["metadata_analysis"]["contract_term"]
        )

        self.assertEqual(
            item["preliminary_scoring"]["profile_name"],
            "Discover Aluminium",
        )

        criteria = {
            criterion["code"]:
                criterion
            for criterion
            in item[
                "preliminary_scoring"
            ]["criteria"]
        }

        self.assertEqual(
            criteria["category"]["status"],
            "matched",
        )

        self.assertEqual(
            criteria["budget"]["status"],
            "not_scored",
        )

        self.assertEqual(
            payload["attempted_sources"],
            [
                "ted",
                "uk_fts",
            ],
        )

        self.assertEqual(
            payload["successful_sources"],
            [
                "ted",
                "uk_fts",
            ],
        )

        self.assertEqual(
            payload["failed_sources"],
            [],
        )

        self.assertFalse(
            payload["partial_failure"]
        )

        self.assertFalse(
            payload["total_failure"]
        )

        self.assertEqual(
            self.catalog.calls[-1][
                "search_terms"
            ],
            ("aluminium",),
        )

        # Discovery is search, not seen-state mutation:
        # repeating it must still return the opportunity.
        repeated = self.client.post(
            self.base(
                "/discover/tenders"
            )
        )

        self.assertEqual(
            repeated.status_code,
            200,
            repeated.text,
        )

        self.assertEqual(
            len(
                repeated.json()["items"]
            ),
            1,
        )

        self.assertEqual(
            len(self.catalog.calls),
            2,
        )

        self.as_account(
            self.outsider
        )

        denied = self.client.post(
            self.base(
                "/discover/tenders"
            )
        )

        self.assertEqual(
            denied.status_code,
            403,
        )

    def test_monitoring_context_is_shared_and_company_scoped(self):
        self.as_account(self.owner)

        first = self.create_company(
            "Monitor One",
            "aluminium",
        )

        second = self.create_company(
            "Monitor Two",
            "aluminium",
        )

        self.as_account(self.viewer)

        status_response = self.client.get(
            self.base("/monitoring/status")
        )

        self.assertEqual(
            status_response.status_code,
            200,
            status_response.text,
        )
        self.assertEqual(
            status_response.json()["active_company"],
            "Monitor One",
        )
        self.assertEqual(
            status_response.json()["feed_mode"],
            "company-profile",
        )
        self.assertEqual(
            status_response.json()["rss_feeds"],
            1,
        )

        denied = self.client.post(
            self.base("/monitoring/scan")
        )
        self.assertEqual(
            denied.status_code,
            403,
        )

        self.as_account(self.member)

        first_scan = self.client.post(
            self.base("/monitoring/scan")
        )

        self.assertEqual(
            first_scan.status_code,
            200,
            first_scan.text,
        )
        self.assertEqual(
            len(first_scan.json()),
            1,
        )

        self.as_account(self.owner)

        repeated = self.client.post(
            self.base("/monitoring/scan")
        )

        self.assertEqual(
            repeated.status_code,
            200,
            repeated.text,
        )
        self.assertEqual(
            repeated.json(),
            [],
        )

        switched = self.client.post(
            self.base(
                f"/companies/{second['id']}/activate"
            )
        )
        self.assertEqual(
            switched.status_code,
            200,
            switched.text,
        )

        self.as_account(self.member)

        second_scope_scan = self.client.post(
            self.base("/monitoring/scan")
        )

        self.assertEqual(
            second_scope_scan.status_code,
            200,
            second_scope_scan.text,
        )
        self.assertEqual(
            len(second_scope_scan.json()),
            1,
        )

        self.assertNotEqual(
            first["id"],
            second["id"],
        )

    def test_outsider_and_api_key_cannot_use_org_workflows(self):
        self.as_account(self.owner)
        self.create_company(
            "Access Test",
            "aluminium",
        )

        self.as_account(self.outsider)

        scoring = self.client.post(
            self.base("/scoring/evaluate"),
            json=self.analysis(),
        )
        self.assertEqual(
            scoring.status_code,
            403,
        )

        status_response = self.client.get(
            self.base("/monitoring/status")
        )
        self.assertEqual(
            status_response.status_code,
            403,
        )

        scan = self.client.post(
            self.base("/monitoring/scan")
        )
        self.assertEqual(
            scan.status_code,
            403,
        )

        self.client.cookies.clear()

        api_key_only = self.client.get(
            self.base("/monitoring/status"),
            headers={
                "X-API-Key": "legacy-secret",
            },
        )

        self.assertEqual(
            api_key_only.status_code,
            401,
        )

    def test_membership_revocation_blocks_dedup_write_after_fetch(self):
        import asyncio

        from app.companies.repository import ORGANIZATION_OWNER_OFFSET
        from app.monitoring import MonitoringAuthorizationError

        self.as_account(self.owner)

        company = self.create_company(
            "Revocation Test",
            "aluminium",
        )

        workspace = self.companies.active_for_organization(
            self.owner.id,
            self.organization.id,
        )
        self.assertIsNotNone(workspace)

        matches = asyncio.run(
            self.monitoring.fetch_matches_for_profile(
                workspace.profile,
            )
        )
        self.assertEqual(
            len(matches),
            1,
        )

        self.organizations.remove_membership(
            self.organization.id,
            self.member.id,
        )

        organization_owner_id = (
            ORGANIZATION_OWNER_OFFSET
            + self.organization.id
        )
        dedup_source = (
            f"eis:company:{company['id']}"
        )

        with self.assertRaises(
            MonitoringAuthorizationError
        ):
            asyncio.run(
                self.monitoring.claim_new_for_organization(
                    account_id=self.member.id,
                    organization_id=self.organization.id,
                    owner_user_id=organization_owner_id,
                    company_scope=str(company["id"]),
                    matches=matches,
                )
            )

        self.assertFalse(
            self.monitoring_repository.seen(
                organization_owner_id,
                dedup_source,
                "shared-notice-1",
            )
        )

    def test_organization_monitoring_state_isolated_from_legacy_owner(self):
        import asyncio

        from app.companies.repository import ORGANIZATION_OWNER_OFFSET

        self.as_account(self.owner)

        company = self.create_company(
            "Isolation Test",
            "aluminium",
        )

        organization_scan = self.client.post(
            self.base("/monitoring/scan")
        )

        self.assertEqual(
            organization_scan.status_code,
            200,
            organization_scan.text,
        )
        self.assertEqual(
            len(organization_scan.json()),
            1,
        )

        organization_owner_id = (
            ORGANIZATION_OWNER_OFFSET
            + self.organization.id
        )
        organization_source = (
            f"eis:company:{company['id']}"
        )

        self.assertTrue(
            self.monitoring_repository.seen(
                organization_owner_id,
                organization_source,
                "shared-notice-1",
            )
        )

        self.assertFalse(
            self.monitoring_repository.seen(
                self.owner.owner_user_id,
                "eis",
                "shared-notice-1",
            )
        )

        self.assertIsNone(
            self.monitoring_repository.get_subscription(
                organization_owner_id
            )
        )

        workspace = self.companies.active_for_organization(
            self.owner.id,
            self.organization.id,
        )

        matches = asyncio.run(
            self.monitoring.fetch_matches_for_profile(
                workspace.profile,
            )
        )

        legacy_first = asyncio.run(
            self.monitoring.claim_new(
                self.owner.owner_user_id,
                matches,
            )
        )

        self.assertEqual(
            len(legacy_first),
            1,
        )

        self.assertTrue(
            self.monitoring_repository.seen(
                self.owner.owner_user_id,
                "eis",
                "shared-notice-1",
            )
        )

        repeated_org_scan = self.client.post(
            self.base("/monitoring/scan")
        )

        self.assertEqual(
            repeated_org_scan.status_code,
            200,
            repeated_org_scan.text,
        )
        self.assertEqual(
            repeated_org_scan.json(),
            [],
        )

    def test_cross_origin_workflow_posts_are_rejected(self):
        self.as_account(self.owner)

        self.create_company(
            "Origin Test",
            "aluminium",
        )

        scoring = self.client.post(
            self.base("/scoring/evaluate"),
            json=self.analysis(),
            headers={
                "Origin": "https://evil.example",
                "Sec-Fetch-Site": "cross-site",
            },
        )

        self.assertEqual(
            scoring.status_code,
            403,
        )

        scan = self.client.post(
            self.base("/monitoring/scan"),
            headers={
                "Origin": "https://evil.example",
                "Sec-Fetch-Site": "cross-site",
            },
        )

        self.assertEqual(
            scan.status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
