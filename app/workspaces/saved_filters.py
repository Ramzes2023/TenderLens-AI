"""Named Discovery view presets. They do NOT fetch feeds or subscribe to notifications."""
from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime, timezone

STAGES = ("keyword", "source", "buyer", "currency", "value", "fit", "deadline", "published")
WRITE_ROLES = {"owner", "admin", "member"}


class PresetPermissionError(Exception):
    pass


class PresetLimitError(Exception):
    pass


class PresetMissingError(Exception):
    pass


def normalized_filters(filters):
    if not isinstance(filters, dict) or set(filters) != set(STAGES):
        raise ValueError("Expected exactly the eight Discovery filter fields.")
    result = {}
    for field in STAGES:
        raw = filters[field]
        if not isinstance(raw, str) or len(raw) > 160:
            raise ValueError("Invalid Discovery filter value.")
        val = raw.strip()
        if any(ord(ch) < 32 for ch in val):
            raise ValueError("Control characters are not allowed.")
        if field in ("source", "currency") and val:
            import re
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", val):
                raise ValueError("Unknown source or currency format.")
        if field in ("deadline", "published") and val:
            from datetime import date
            if len(val) != 10 or date.fromisoformat(val).isoformat() != val:
                raise ValueError("Dates must be YYYY-MM-DD.")
        if field in ("fit", "value") and val:
            from decimal import Decimal, InvalidOperation
            try:
                x = Decimal(val)
            except InvalidOperation:
                raise ValueError("Invalid numeric filter.") from None
            if not x.is_finite() or x < 0 or x > (100 if field == "fit" else 1e15):
                raise ValueError("Filter outside supported range.")
            if val.startswith("+") or "e" in val.lower():
                raise ValueError("Scientific numeric notation is unsupported.")
        result[field] = val
    if result["value"] and not result["currency"]:
        raise ValueError("Currency is required for a minimum price filter.")
    return result


class SavedSearchPresets:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def _scope(conn, account_id, organization_id, company_id, *, write):
        membership = conn.execute(
            "SELECT role FROM organization_members WHERE account_id=? AND organization_id=?",
            (account_id, organization_id),
        ).fetchone()
        if membership is None or (write and membership["role"] not in WRITE_ROLES):
            raise PresetPermissionError()
        company = conn.execute(
            "SELECT id FROM company_workspaces WHERE id=? AND organization_id=?",
            (company_id, organization_id),
        ).fetchone()
        if company is None:
            raise PresetPermissionError()

    @staticmethod
    def _row(row):
        return {
            "id": int(row["id"]), "name": row["name"],
            "filters": json.loads(row["filters_json"]),
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "delivery": "not_configured",
        }

    def list(self, *, account_id, organization_id, company_id):
        with closing(self.database.connect()) as conn:
            self._scope(conn, account_id, organization_id, company_id, write=False)
            rows = conn.execute(
                "SELECT * FROM saved_search_filters WHERE account_id=? "
                "AND organization_id=? AND company_id=? "
                "ORDER BY updated_at DESC,id DESC LIMIT 20",
                (account_id, organization_id, company_id),
            ).fetchall()
            return [self._row(row) for row in rows]

    def save(self, *, account_id, organization_id, company_id, name, filters):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError("Preset name must be 1-80 characters.")
        clean_name = name.strip()
        if any(ord(ch) < 32 for ch in clean_name):
            raise ValueError("Invalid preset name.")
        cleaned = normalized_filters(filters)
        encoded = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with closing(self.database.connect()) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                self._scope(conn, account_id, organization_id, company_id, write=True)
                existing = conn.execute(
                    "SELECT id FROM saved_search_filters WHERE account_id=? AND organization_id=? "
                    "AND company_id=? AND name=?",
                    (account_id, organization_id, company_id, clean_name),
                ).fetchone()
                if existing is None:
                    count = conn.execute(
                        "SELECT COUNT(*) FROM saved_search_filters WHERE account_id=? "
                        "AND organization_id=? AND company_id=?",
                        (account_id, organization_id, company_id),
                    ).fetchone()[0]
                    if count >= 20:
                        raise PresetLimitError()
                conn.execute(
                    "INSERT INTO saved_search_filters "
                    "(organization_id,company_id,account_id,name,filters_json,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?) "
                    "ON CONFLICT(organization_id,company_id,account_id,name) "
                    "DO UPDATE SET filters_json=excluded.filters_json, updated_at=excluded.updated_at",
                    (organization_id, company_id, account_id, clean_name, encoded, now, now),
                )
                row = conn.execute(
                    "SELECT * FROM saved_search_filters WHERE account_id=? AND organization_id=? "
                    "AND company_id=? AND name=?",
                    (account_id, organization_id, company_id, clean_name),
                ).fetchone()
                return self._row(row)

    def delete(self, *, account_id, organization_id, company_id, preset_id):
        with closing(self.database.connect()) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                self._scope(conn, account_id, organization_id, company_id, write=True)
                result = conn.execute(
                    "DELETE FROM saved_search_filters WHERE id=? AND account_id=? "
                    "AND organization_id=? AND company_id=?",
                    (preset_id, account_id, organization_id, company_id),
                )
                if result.rowcount == 0:
                    raise PresetMissingError()
