"""Read-only EIS source revision history visible only to saved-company members.

The underlying connector worker writes versioned source observations.
No synthetic change events, document-diff claims or upstream network checks.
"""
from __future__ import annotations
import json
from contextlib import closing
from app.workspaces.lifecycle import SavedTenderWorkflow


class SavedSourceHistory:
    def __init__(self,database): self.database=database

    def get(self,*,account_id,organization_id,company_id,saved_id):
        with closing(self.database.connect()) as conn:
            SavedTenderWorkflow._scope(conn,account_id,organization_id,
                company_id,saved_id,write=False)
            saved=conn.execute(
                "SELECT source,external_id FROM saved_opportunities "
                "WHERE id=? AND organization_id=? AND company_id=?",
                (saved_id,organization_id,company_id)).fetchone()
            if saved["source"] not in {"eis","eis_223"}:
                return {"supported":False,"source":saved["source"],
                        "revisions":[],"has_document_evidence":False}
            rows=conn.execute(
                "SELECT revision,connector_version,observed_at,comparison_json "
                "FROM source_notice_observations WHERE source_id=? AND external_id=? "
                "ORDER BY observed_at DESC,revision DESC LIMIT 25",
                (saved["source"],saved["external_id"])).fetchall()
            results=[]
            for row in rows:
                if not row["comparison_json"] or len(row["comparison_json"])>65536:
                    raise ValueError("Invalid observation evidence size.")
                info=json.loads(row["comparison_json"])
                if not isinstance(info,dict) or info.get("status") not in {
                    "first_observation","changed","unchanged","insufficient_data",
                    "identity_mismatch","out_of_order"
                } or not isinstance(info.get("changes"),list):
                    raise ValueError("Invalid source observation evidence.")
                changes=[]
                for change in info["changes"][:20]:
                    if not isinstance(change,dict):
                        raise ValueError("Invalid observation change.")
                    if change.get("field") in {"title","buyer","price","currency","deadline"} and (
                        change.get("change_type") in {"added","modified","removed"}):
                        changes.append({"field":change["field"],"type":change["change_type"]})
                results.append({"revision":str(row["revision"])[:64],
                                "observed_at":str(row["observed_at"])[:45],
                                "connector_version":str(row["connector_version"])[:100],
                                "status":info["status"],"changed_fields":changes})
            return {"supported":True,"source":saved["source"],
                    "revisions":results,"has_document_evidence":False}
