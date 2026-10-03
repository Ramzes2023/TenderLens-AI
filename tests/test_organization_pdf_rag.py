import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.security import SESSION_COOKIE
from app.auth import AuthRepository, AuthService
from app.companies import (
    CompanyRepository,
    CompanyService,
)
from app.database import TenderRepository
from app.models.tender import TenderAnalysis
from app.organizations import (
    OrganizationRepository,
    OrganizationService,
    Role,
)
from app.parsers.pdf import PdfSummary
from app.scoring.models import CompanyProfile
from app.tenancy import organization_owner_id


class FakeProvider:
    async def generate(
        self,
        prompt,
        *,
        max_tokens=512,
    ):
        raise AssertionError(
            "Unexpected provider call."
        )


class FakeRag:
    def __init__(self):
        self.index_calls = []
        self.answer_calls = []
        self.on_index = None
        self.on_answer = None

    def index_pdf_for_organization(
        self,
        organization_id,
        pdf_sha256,
        summary,
    ):
        self.index_calls.append(
            (
                organization_id,
                pdf_sha256,
                summary.text,
            )
        )

        if self.on_index is not None:
            self.on_index()

        return 2

    async def answer_for_organization(
        self,
        organization_id,
        pdf_sha256,
        question,
        provider,
    ):
        self.answer_calls.append(
            (
                organization_id,
                pdf_sha256,
                question,
            )
        )

        if self.on_answer is not None:
            self.on_answer()

        source = SimpleNamespace(
            chunk_index=0,
            page_number=1,
            text="???? ???????? 20 ????.",
            score=0.95,
        )

        return SimpleNamespace(
            answer="???? ???????? 20 ???? [???. 1].",
            sources=(source,),
        )


class OrganizationPdfRagTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.path = (
            Path(self.temp.name)
            / "organization-pdf-rag.db"
        )

        auth_repository = AuthRepository(self.path)
        auth_repository.initialize()

        self.org_repo = OrganizationRepository(
            self.path
        )
        self.org_repo.initialize()

        company_repository = CompanyRepository(
            self.path
        )
        company_repository.initialize()

        self.tenders = TenderRepository(
            self.path
        )
        self.tenders.initialize()

        self.auth = AuthService(
            auth_repository
        )

        self.organizations = OrganizationService(
            self.org_repo
        )

        self.companies = CompanyService(
            company_repository
        )

        self.owner = self.auth.register(
            "pdf-owner@example.com",
            "very secure password 123",
        )

        self.member = self.auth.register(
            "pdf-member@example.com",
            "very secure password 123",
        )

        self.viewer = self.auth.register(
            "pdf-viewer@example.com",
            "very secure password 123",
        )

        self.outsider = self.auth.register(
            "pdf-outsider@example.com",
            "very secure password 123",
        )

        self.organization = self.org_repo.create(
            "PDF Organization",
            self.owner.id,
        )

        self.org_repo.add_membership(
            self.organization.id,
            self.member.id,
            Role.MEMBER,
        )

        self.org_repo.add_membership(
            self.organization.id,
            self.viewer.id,
            Role.VIEWER,
        )

        self.profile = CompanyProfile(
            profile_version="org-pdf-test",
            company_name="Organization Profile",
            business_mode="sell",
            product_keywords=[
                "aluminium profile",
            ],
            search_keywords=[
                "aluminium profile",
            ],
            accepted_currencies=["RUB"],
        )

        self.companies.create_for_organization(
            self.owner,
            self.organization.id,
            "Organization Profile",
            self.profile,
        )

        self.rag = FakeRag()

        runtime = ApiRuntime(
            provider=FakeProvider(),
            auth_service=self.auth,
            organization_service=self.organizations,
            company_service=self.companies,
            tender_repository=self.tenders,
            rag_service=self.rag,
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

        token = self.auth.create_session(
            account
        )

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
    def summary():
        return PdfSummary(
            "ok",
            2,
            100,
            0,
            (
                "Supply of aluminium profile. "
                "Delivery period 20 days."
            ),
            (
                "Supply of aluminium profile.",
                "Delivery period 20 days.",
            ),
        )

    @staticmethod
    def result():
        return SimpleNamespace(
            analysis=TenderAnalysis(
                title="Supply of aluminium profile",
                tender_number="ORG-PDF-1",
                customer="Organization Customer",
                initial_price=1_000_000,
                currency="RUB",
                procurement_object=(
                    "aluminium profile"
                ),
            ),
            truncated=False,
        )

    def save_record(
        self,
        account,
        organization_id,
        digest,
        title="Existing organization tender",
    ):
        return self.tenders.save_success_for_organization(
            account_id=account.id,
            organization_id=organization_id,
            pdf_sha256=digest,
            source_filename="existing.pdf",
            pages=1,
            characters=50,
            analysis=TenderAnalysis(
                title=title,
                procurement_object=(
                    "aluminium profile"
                ),
            ),
            scoring=None,
            analysis_truncated=False,
        )

    def test_member_pdf_analysis_persists_shared_record_and_indexes_rag(self):
        self.as_account(self.member)

        data = b"%PDF-organization-analysis"

        with (
            patch(
                "app.api.organization_data_routes.summarize_pdf",
                new=AsyncMock(
                    return_value=self.summary()
                ),
            ),
            patch(
                "app.api.organization_data_routes.analyze_tender",
                new=AsyncMock(
                    return_value=self.result()
                ),
            ),
        ):
            response = self.client.post(
                self.base("/analysis/pdf"),
                files={
                    "file": (
                        "organization.pdf",
                        data,
                        "application/pdf",
                    )
                },
            )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        body = response.json()

        self.assertFalse(
            body["duplicate"]
        )

        self.assertEqual(
            body["scoring"]["profile_name"],
            "Organization Profile",
        )

        self.assertEqual(
            body["rag_indexed_chunks"],
            2,
        )

        digest = hashlib.sha256(
            data
        ).hexdigest()

        self.assertEqual(
            self.rag.index_calls[0][0],
            self.organization.id,
        )

        self.assertEqual(
            self.rag.index_calls[0][1],
            digest,
        )

        self.as_account(self.owner)

        history = self.client.get(
            self.base("/tenders")
        )

        self.assertEqual(
            history.status_code,
            200,
            history.text,
        )

        self.assertEqual(
            history.json()[0]["pdf_sha256"],
            digest,
        )

    def test_duplicate_reuses_analysis_without_pdf_or_llm_work(self):
        data = b"%PDF-organization-duplicate"

        digest = hashlib.sha256(
            data
        ).hexdigest()

        existing = self.save_record(
            self.owner,
            self.organization.id,
            digest,
        )

        self.as_account(self.member)

        with (
            patch(
                "app.api.organization_data_routes.summarize_pdf",
                new=AsyncMock(
                    side_effect=AssertionError(
                        "Duplicate PDF should not be parsed."
                    )
                ),
            ),
            patch(
                "app.api.organization_data_routes.analyze_tender",
                new=AsyncMock(
                    side_effect=AssertionError(
                        "Duplicate PDF should not call LLM."
                    )
                ),
            ),
        ):
            response = self.client.post(
                self.base("/analysis/pdf"),
                files={
                    "file": (
                        "duplicate.pdf",
                        data,
                        "application/pdf",
                    )
                },
            )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        self.assertTrue(
            response.json()["duplicate"]
        )

        self.assertEqual(
            response.json()["record_id"],
            existing.id,
        )

        self.assertEqual(
            self.rag.index_calls,
            [],
        )

    def test_viewer_cannot_upload_but_can_use_shared_rag(self):
        data = b"%PDF-viewer-forbidden"

        self.as_account(self.viewer)

        denied = self.client.post(
            self.base("/analysis/pdf"),
            files={
                "file": (
                    "viewer.pdf",
                    data,
                    "application/pdf",
                )
            },
        )

        self.assertEqual(
            denied.status_code,
            403,
        )

        digest = "a" * 64

        self.save_record(
            self.owner,
            self.organization.id,
            digest,
        )

        answer = self.client.post(
            self.base("/rag/ask"),
            json={
                "pdf_sha256": digest,
                "question":
                    "????? ???? ?????????",
            },
        )

        self.assertEqual(
            answer.status_code,
            200,
            answer.text,
        )

        self.assertIn(
            "20 ????",
            answer.json()["answer"],
        )

        self.assertEqual(
            self.rag.answer_calls[0][0],
            self.organization.id,
        )

    def test_cross_organization_rag_is_hidden_and_legacy_api_cannot_guess(self):
        second = self.org_repo.create(
            "Foreign RAG Organization",
            self.outsider.id,
        )

        digest = "b" * 64

        self.save_record(
            self.outsider,
            second.id,
            digest,
            "Foreign organization tender",
        )

        self.as_account(self.owner)

        hidden = self.client.post(
            self.base("/rag/ask"),
            json={
                "pdf_sha256": digest,
                "question": "Hidden?",
            },
        )

        self.assertEqual(
            hidden.status_code,
            404,
        )

        self.assertEqual(
            self.rag.answer_calls,
            [],
        )

        self.client.cookies.clear()

        legacy = self.client.post(
            "/api/v1/rag/ask",
            json={
                "owner_user_id":
                    organization_owner_id(
                        self.organization.id
                    ),
                "pdf_sha256": digest,
                "question": "Can legacy read it?",
            },
            headers={
                "X-API-Key": "legacy-secret",
            },
        )

        self.assertEqual(
            legacy.status_code,
            403,
        )

    def test_membership_revocation_before_final_pdf_save_blocks_persistence_and_rag(self):
        from app.scoring.engine import (
            score_tender as real_score_tender,
        )

        self.as_account(self.member)

        data = b"%PDF-revoked-before-save"

        digest = hashlib.sha256(
            data
        ).hexdigest()

        def revoke_then_score(
            analysis,
            profile,
        ):
            self.org_repo.remove_membership(
                self.organization.id,
                self.member.id,
            )

            return real_score_tender(
                analysis,
                profile,
            )

        with (
            patch(
                "app.api.organization_data_routes.summarize_pdf",
                new=AsyncMock(
                    return_value=self.summary()
                ),
            ),
            patch(
                "app.api.organization_data_routes.analyze_tender",
                new=AsyncMock(
                    return_value=self.result()
                ),
            ),
            patch(
                "app.api.organization_data_routes.score_tender",
                side_effect=revoke_then_score,
            ),
        ):
            response = self.client.post(
                self.base("/analysis/pdf"),
                files={
                    "file": (
                        "revoked.pdf",
                        data,
                        "application/pdf",
                    )
                },
            )

        self.assertEqual(
            response.status_code,
            403,
            response.text,
        )

        self.assertEqual(
            self.rag.index_calls,
            [],
        )

        missing = self.tenders.find_by_hash_for_organization(
            self.owner.id,
            self.organization.id,
            digest,
        )

        self.assertIsNone(
            missing
        )

    def test_revocation_during_rag_indexing_blocks_pdf_response(self):
        self.as_account(self.member)

        data = b"%PDF-revoked-during-rag-index"

        digest = hashlib.sha256(
            data
        ).hexdigest()

        def revoke():
            self.org_repo.remove_membership(
                self.organization.id,
                self.member.id,
            )

        self.rag.on_index = revoke

        with (
            patch(
                "app.api.organization_data_routes.summarize_pdf",
                new=AsyncMock(
                    return_value=self.summary()
                ),
            ),
            patch(
                "app.api.organization_data_routes.analyze_tender",
                new=AsyncMock(
                    return_value=self.result()
                ),
            ),
        ):
            response = self.client.post(
                self.base("/analysis/pdf"),
                files={
                    "file": (
                        "revoked-during-index.pdf",
                        data,
                        "application/pdf",
                    )
                },
            )

        self.assertEqual(
            response.status_code,
            403,
            response.text,
        )

        self.assertEqual(
            len(self.rag.index_calls),
            1,
        )

        # Persistence completed while membership was still valid.
        # The data belongs to the organization and must not be
        # rolled back merely because this account was later removed.
        stored = self.tenders.find_by_hash_for_organization(
            self.owner.id,
            self.organization.id,
            digest,
        )

        self.assertIsNotNone(
            stored
        )

    def test_revocation_during_rag_answer_blocks_response(self):
        digest = "c" * 64

        self.save_record(
            self.owner,
            self.organization.id,
            digest,
        )

        self.as_account(self.member)

        def revoke():
            self.org_repo.remove_membership(
                self.organization.id,
                self.member.id,
            )

        self.rag.on_answer = revoke

        response = self.client.post(
            self.base("/rag/ask"),
            json={
                "pdf_sha256": digest,
                "question":
                    "????? ?????",
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.assertEqual(
            len(self.rag.answer_calls),
            1,
        )

    def test_cross_origin_pdf_and_rag_posts_are_rejected(self):
        self.as_account(self.owner)

        headers = {
            "Origin": "https://evil.example",
            "Sec-Fetch-Site": "cross-site",
        }

        pdf = self.client.post(
            self.base("/analysis/pdf"),
            files={
                "file": (
                    "blocked.pdf",
                    b"%PDF-blocked",
                    "application/pdf",
                )
            },
            headers=headers,
        )

        self.assertEqual(
            pdf.status_code,
            403,
        )

        rag = self.client.post(
            self.base("/rag/ask"),
            json={
                "pdf_sha256": "d" * 64,
                "question": "Blocked?",
            },
            headers=headers,
        )

        self.assertEqual(
            rag.status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
