from pathlib import Path

from app.api.dashboard import dashboard_html


ROOT = Path(__file__).resolve().parents[1]


def test_saved_opportunities_is_real_workspace_page():
    html = dashboard_html()

    assert 'id="savedWorkspace"' in html
    assert 'data-page="saved"' in html
    assert 'Saved opportunities' in html
    assert '/assets/saved.js?v=phase24r' in html
    assert 'The Saved Opportunities page is coming next.' not in html


def test_saved_ui_uses_existing_company_scoped_shortlist_api():
    js = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "saved.js"
    ).read_text(
        encoding="utf-8"
    )

    assert "/shortlist" in js
    assert "method:'DELETE'" in js
    assert "credentials:'same-origin'" in js
    assert "cache:'no-store'" in js
    assert "ValyqonDiscovery" in js
    assert "activeCompanyId" in js


def test_discover_refreshes_saved_state_when_reopened():
    js = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "discovery.js"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "location.hash.slice(1)||'overview'"
        in js
    )
    assert (
        "==='discover')loadShortlist()"
        in js
    )


def test_saved_full_ai_uses_existing_pdf_pipeline():
    js = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "saved.js"
    ).read_text(
        encoding="utf-8"
    )

    required = [
        "async function analyzeSavedTenderPdf",
        "new FormData()",
        "form.append(",
        "/analysis/pdf",
        "method:'POST'",
        "credentials:'same-origin'",
        "renderer.applyFullAiResult",
        "/shortlist",
        "body:JSON.stringify(",
        "canWriteWorkspace()",
        "savedRequestStillCurrent",
        "scope===identity()",
        "ticket===serial",
        "expectedOpportunity",
        "savedId",
        "analysisResponse.status===403",
        "analysisResponse.status===409",
        "analysisResponse.status===413",
        "analysisResponse.status===415",
        "analysisResponse.status===422",
        "saveResponse.status===403",
        "saveResponse.status===409",
    ]

    for value in required:
        assert value in js, value


def test_saved_full_ai_has_no_remote_document_download():
    js = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "saved.js"
    ).read_text(
        encoding="utf-8"
    )

    forbidden = [
        "document_url",
        "attachment_url",
        "remoteDocumentUrl",
        "fetch(record.opportunity.url",
        "fetch(item.url",
    ]

    for value in forbidden:
        assert value not in js, value


def test_saved_full_ai_is_permission_and_scope_guarded():
    js = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "saved.js"
    ).read_text(
        encoding="utf-8"
    )

    assert "canWriteWorkspace()" in js
    assert "!canWriteWorkspace()" in js
    assert "savedRequestStillCurrent" in js
    assert "Number(current?.id)===savedId" in js
    assert "opportunityKey(" in js


def test_pdf_workflow_assets_are_cache_busted():
    html = dashboard_html()

    assert (
        "/assets/discovery.js?"
        "v=phase24r"
        in html
    )

    assert (
        "/assets/saved.js?"
        "v=phase24r"
        in html
    )


def test_history_remains_read_only_for_full_ai():
    history = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "history.js"
    ).read_text(
        encoding="utf-8"
    )

    assert "/analysis/pdf" not in history
    assert "new FormData()" not in history
    assert "renderer.detail(item)" in history
