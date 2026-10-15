from pathlib import Path

from app.api.schemas import TenderDiscoveryItem
from app.models.tender import TenderAnalysis
from app.scoring.models import (
    CriterionResult,
    ScoringResult,
)


def scoring():
    return ScoringResult(
        profile_version="1",
        profile_name="Pump Company",
        fit_score=82,
        completeness_percent=90,
        scorable_weight=30,
        criteria=[
            CriterionResult(
                code="category",
                label="Category",
                weight=30,
                earned_points=25,
                status="matched",
                explanation="Strong match.",
                evidence=[
                    "industrial pumps",
                ],
            )
        ],
        missing_information=[],
        document_risks=[],
        stop_factors=[],
    )


def metadata_item():
    return TenderDiscoveryItem(
        source="ted",
        external_id="notice-24l",
        title="Pump procurement",
        url="https://example.test/tender",
        reasons=[
            "Product keyword matched.",
        ],
        currency="EUR",
        analysis_stage="metadata_preview",
        metadata_analysis=TenderAnalysis(
            title="Pump procurement",
            procurement_object="industrial pumps",
        ),
        preliminary_scoring=scoring(),
    )


def test_discovery_item_is_metadata_only_by_default():
    item = metadata_item()

    assert item.analysis_stage == (
        "metadata_preview"
    )

    assert item.full_ai_analyzed is False
    assert item.full_analysis is None
    assert item.full_scoring is None
    assert item.full_analysis_record_id is None
    assert item.full_analysis_pdf_sha256 is None
    assert item.full_analysis_source_filename is None
    assert item.full_analysis_truncated is None
    assert item.full_analysis_warnings == []


def test_full_document_analysis_round_trips_in_shortlist_snapshot_contract():
    item = metadata_item().model_copy(
        update={
            "analysis_stage":
                "full_ai_document",
            "full_ai_analyzed":
                True,
            "full_analysis":
                TenderAnalysis(
                    title="Pump procurement",
                    tender_number="T-24L",
                    procurement_object=(
                        "industrial centrifugal pumps"
                    ),
                    required_documents=[
                        "ISO 9001 certificate",
                    ],
                    technical_requirements=[
                        "Flow rate 500 m3/h",
                    ],
                    risks=[
                        "Short delivery period",
                    ],
                ),
            "full_scoring":
                scoring(),
            "full_analysis_record_id":
                42,
            "full_analysis_pdf_sha256":
                "a" * 64,
            "full_analysis_source_filename":
                "official-tender.pdf",
            "full_analysis_truncated":
                False,
            "full_analysis_warnings":
                [],
        }
    )

    restored = (
        TenderDiscoveryItem
        .model_validate_json(
            item.model_dump_json()
        )
    )

    assert restored.full_ai_analyzed is True

    assert restored.analysis_stage == (
        "full_ai_document"
    )

    assert (
        restored
        .full_analysis
        .required_documents
        == ["ISO 9001 certificate"]
    )

    assert (
        restored
        .full_analysis
        .technical_requirements
        == ["Flow rate 500 m3/h"]
    )

    assert (
        restored
        .full_scoring
        .fit_score
        == 82
    )

    assert (
        restored
        .full_analysis_record_id
        == 42
    )

    assert (
        restored
        .full_analysis_source_filename
        == "official-tender.pdf"
    )


def test_discovery_browser_full_ai_source_contract():
    js = Path(
        "app/api/static/discovery.js"
    ).read_text(
        encoding="utf-8"
    )

    required = [
        "async function analyzeTenderPdf",
        "new FormData()",
        "form.append(",
        "/analysis/pdf",
        "method:'POST'",
        "credentials:'same-origin'",
        "applyFullAiResult(",
        "analysis_stage:'full_ai_document'",
        "full_ai_analyzed:true",
        "full_analysis:result.analysis",
        "full_scoring:result.scoring||null",
        "syncFullAiSavedSnapshot",
        "/shortlist",
        "data-full-ai=",
        "accept=\".pdf,application/pdf\"",
        "10*1024*1024",
        "canWriteWorkspace()",
        "scope!==identity()",
        "runSerial!==serial",
        "response.status===403",
        "response.status===413",
        "response.status===415",
        "response.status===422",
    ]

    for value in required:
        assert value in js, value

    # Browser workflow must use a user-selected PDF,
    # not silently retrieve arbitrary remote files.
    forbidden = [
        "document_url",
        "attachment_url",
        "remoteDocumentUrl",
        "fetch(item.url",
        "fetch(item.document",
    ]

    for value in forbidden:
        assert value not in js, value


def test_discovery_ui_uses_existing_organization_pdf_pipeline():
    js = Path(
        "app/api/static/discovery.js"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "/analysis/pdf"
        in js
    )

    assert (
        "new FormData()"
        in js
    )

    assert (
        "applyFullAiResult"
        in js
    )

    assert (
        "full_ai_document"
        in js
    )

    assert (
        "syncFullAiSavedSnapshot"
        in js
    )

    assert (
        "/shortlist"
        in js
    )

    assert (
        "Analyze tender PDF"
        in js
    )

    # The Discovery browser workflow must not
    # invent a remote tender-document URL.
    assert (
        "document_url"
        not in js
    )

    assert (
        "attachment_url"
        not in js
    )
