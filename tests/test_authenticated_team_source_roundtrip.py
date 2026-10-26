"""Isolated authenticated API E2E for tender team features and notice revisions.

Only a disposable SQLite database and OFFLINE_FIXTURE records. No real sources,
emails, production credentials or claim of a Chromium/browser pass.
"""
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
import json

from app.database.backend import Database
from app.database.config import DatabaseSettings
from scripts import phase24_v6_customer_browser_acceptance as customer_api
from app.sources.models import TenderNotice
from app.sources.observations import record_observation


def test_full_authenticated_team_and_eis_history_roundtrip():
    with customer_api.isolated_customer() as customer:
        db=Database(DatabaseSettings("",customer.path))
        db.migrate()
        customer.client.app.state.runtime.database=db
        customer_api.login(customer,customer.owner)
        company=customer_api.create_company(customer)
        org=customer.organization.id

        with closing(db.connect()) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO saved_opportunities "
                    "(organization_id,company_id,source,external_id,snapshot_json,"
                    "created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                    (org,company["id"],"eis","OFFLINE_FIXTURE-001","{}","now","now"))
                saved=conn.execute(
                    "SELECT id FROM saved_opportunities WHERE organization_id=? "
                    "AND company_id=?",(org,company["id"])).fetchone()[0]
        base=f"/api/v1/organizations/{org}/shortlist/{saved}"
        assert customer.client.get(base+"/team").status_code==200
        assert customer.client.get(base+"/team").json()["revision"]==0
        assert customer.client.get(base+"/source-history").json()["revisions"]==[]

        hostile=customer.client.patch(base+"/team",
            json=dict(action="assign",expected_revision=0,
                      assignee_account_id=customer.member.id),
            headers={"Origin":"https://evil.example.invalid","Sec-Fetch-Site":"cross-site"})
        assert hostile.status_code==403
        assert customer.client.get(base+"/team").json()["revision"]==0

        assigned=customer.client.patch(base+"/team",
            json=dict(action="assign",expected_revision=0,
                      assignee_account_id=customer.member.id))
        assert assigned.status_code==200,assigned.text
        assert assigned.json()["assignee_account_id"]==customer.member.id
        assert assigned.json()["revision"]==1
        assert customer.client.patch(base+"/team",
            json=dict(action="assign",expected_revision=0,
                      assignee_account_id=customer.member.id)).status_code==409

        customer_api.login(customer,customer.member)
        requested=customer.client.patch(base+"/team",
            json=dict(action="request",expected_revision=1))
        assert requested.status_code==200,requested.text
        assert requested.json()["approval_state"]=="pending"
        assert customer.client.patch(base+"/team",
            json=dict(action="approve",expected_revision=2)).status_code==403

        customer_api.login(customer,customer.viewer)
        assert customer.client.get(base+"/team").status_code==200
        assert customer.client.patch(base+"/team",
            json=dict(action="reject",expected_revision=2)).status_code==403

        # Promote a real second test account to administrator in this disposable
        # tenant, never a forged X-Role request header.
        with closing(db.connect()) as conn:
            with conn:
                conn.execute(
                    "UPDATE organization_members SET role='admin' "
                    "WHERE organization_id=? AND account_id=?",
                    (org,customer.viewer.id))
        customer_api.login(customer,customer.viewer)
        approval=customer.client.patch(base+"/team",
            json=dict(action="approve",expected_revision=2))
        assert approval.status_code==200,approval.text
        assert approval.json()["approval_state"]=="approved"
        assert approval.json()["decided_by_account_id"]==customer.viewer.id
        events=customer.client.get(base+"/team/events")
        assert events.status_code==200
        assert [x["action"] for x in events.json()]==["approve","request","assign"]

        # Source-worker observation persistence is exercised with explicit
        # synthetic notices. This is NOT proof of live upstream EIS availability.
        version="connector-sync-v1:eis:adapter-r1"
        original=TenderNotice(source="eis",external_id="OFFLINE_FIXTURE-001",
            title="OFFLINE_FIXTURE parts",url="https://example.invalid/tender/001",
            initial_price=1000,currency="RUB")
        changed=TenderNotice(source="eis",external_id="OFFLINE_FIXTURE-001",
            title="OFFLINE_FIXTURE updated parts",url="https://example.invalid/tender/001",
            initial_price=1200,currency="RUB")
        with closing(db.connect()) as conn:
            with conn:
                record_observation(conn,original,
                    json.dumps(asdict(original),ensure_ascii=False),
                    "2026-10-23T12:00:00+00:00",version)
                record_observation(conn,changed,
                    json.dumps(asdict(changed),ensure_ascii=False),
                    "2026-10-23T13:00:00+00:00",version)
        history=customer.client.get(base+"/source-history")
        assert history.status_code==200,history.text
        observed=history.json()
        assert observed["supported"] is True
        assert len(observed["revisions"])==2
        assert observed["revisions"][0]["status"]=="changed"
        assert {r["field"] for r in observed["revisions"][0]["changed_fields"]}=={
            "title","price"}
        assert observed["has_document_evidence"] is False

        customer_api.login(customer,customer.outsider)
        assert customer.client.get(base+"/team").status_code==403
        assert customer.client.get(base+"/source-history").status_code==403
        assert customer.client.patch(base+"/team",
            json=dict(action="request",expected_revision=3)).status_code==403
        db.close()
