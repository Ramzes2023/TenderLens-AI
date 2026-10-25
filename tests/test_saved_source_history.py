"""Read-only source history evidence must be genuine and tenant-isolated."""
import json
from contextlib import closing
from pathlib import Path

import pytest

from app.auth import AuthRepository
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.organizations import OrganizationRepository
from app.workspaces.lifecycle import WorkflowDenied, WorkflowMissing
from app.workspaces.source_history import SavedSourceHistory


def test_saved_history_eis_metadata_with_access_and_ignored_document_guesses(tmp_path):
    db=Database(DatabaseSettings("",tmp_path/"evidence.sqlite"))
    db.migrate()
    accounts=AuthRepository(db)
    owner=accounts.create_account("evidence-owner@example.test","hash")
    outsider=accounts.create_account("evidence-other@example.test","hash")
    org=OrganizationRepository(db).default_for_account(owner.id)
    with closing(db.connect()) as conn:
        with conn:
            for source,external in [("eis","real-123"),("ted","ted-6")]:
                conn.execute("INSERT INTO saved_opportunities "
                    "(organization_id,company_id,source,external_id,snapshot_json,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?)",(org.id,12,source,external,"{}","now","now"))
            saved=conn.execute("SELECT id FROM saved_opportunities WHERE source='eis'").fetchone()[0]
            ted=conn.execute("SELECT id FROM saved_opportunities WHERE source='ted'").fetchone()[0]
            evidence={"status":"changed","changes":[
                {"field":"title","change_type":"modified"},
                {"field":"deadline","change_type":"modified"},
                {"field":"document_ids","change_type":"removed"},
            ]}
            conn.execute("INSERT INTO source_notice_observations "
                "(source_id,external_id,revision,notice_json,connector_version,observed_at,comparison_json) "
                "VALUES (?,?,?,?,?,?,?)",
                ("eis","real-123","r1","{}","connector-sync-v1:eis:adapter-r1",
                 "2026-10-23T18:00:00+00:00",json.dumps(evidence)))
            conn.execute("INSERT INTO source_notice_observations "
                "(source_id,external_id,revision,notice_json,connector_version,observed_at,comparison_json) "
                "VALUES (?,?,?,?,?,?,?)",
                ("eis","someone-else","r2","{}","connector-sync-v1:eis:adapter-r1",
                 "2026-10-23T19:00:00+00:00",json.dumps(evidence)))
    service=SavedSourceHistory(db)
    scope=dict(account_id=owner.id,organization_id=org.id,company_id=12,saved_id=saved)
    result=service.get(**scope)
    assert result["supported"] is True and len(result["revisions"])==1
    assert result["revisions"][0]["changed_fields"]==[
        {"field":"title","type":"modified"},{"field":"deadline","type":"modified"}]
    assert result["has_document_evidence"] is False
    assert "document_ids" not in str(result)
    assert service.get(**{**scope,"saved_id":ted})["supported"] is False
    with pytest.raises(WorkflowDenied):
        service.get(**{**scope,"account_id":outsider.id})
    with pytest.raises(WorkflowMissing):
        service.get(**{**scope,"company_id":13})
    with closing(db.connect()) as conn:
        with conn:
            conn.execute("DELETE FROM source_notice_observations WHERE external_id='real-123'")
    assert service.get(**scope)["revisions"]==[]
    db.close()


def test_source_history_display_contract():
    root=Path(__file__).resolve().parents[1]
    from app.api.dashboard import dashboard_html
    html=dashboard_html()
    assert 'id="savedSourceHistoryPanel"' in html
    assert 'id="savedSourceHistoryEvents"' in html
    assert '/assets/source_history.js' in html
    from app.api.shortlist_workflow_routes import router
    assert any(r.path.endswith("/{saved_id}/source-history") for r in router.routes)
    js=(root/"app/api/static/source_history.js").read_text(encoding="utf-8")
    assert "credentials:'same-origin'" in js
    assert "state.activeCompanyId===selection.companyId" in js
    assert "Missing records never mean" in html
    assert "fetch(url" in js
    assert "PDF" in html
