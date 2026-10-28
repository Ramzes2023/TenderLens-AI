"""Read-only isolated public feed source inventory, never production/network."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.sources.isolated_public_inventory import SOURCE_FLAGS, inventory


def _flags(**overrides):
    flags = {name: "false" for _, name in SOURCE_FLAGS}
    flags.update(overrides)
    return flags


def _db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE source_opportunities "
                 "(source_id TEXT, notice_json TEXT, last_seen TEXT)")
    return conn


def test_per_source_inventory_counts_only_recent_open_previews():
    now = datetime(2026, 10, 28, 16, 30, tzinfo=timezone.utc)
    db = _db()
    try:
        future = (now + timedelta(days=2)).isoformat()
        expired = (now - timedelta(hours=1)).isoformat()
        valid = {"source": "mikroton_tender", "title": "Поставка насосов",
                 "deadline": future, "initial_price": 1000, "currency": "RUB"}
        def add(data, seen=now):
            db.execute("INSERT INTO source_opportunities VALUES (?,?,?)",
                       ("mikroton_tender", json.dumps(data, ensure_ascii=False),
                        seen.isoformat()))
        add(valid)
        add({**valid, "deadline": expired})
        add({**valid, "source": "other"})
        add(valid, now - timedelta(hours=3))
        flags = _flags(MIKROTON_TENDER_ENABLED="true",
                       STAN_COMMERCIAL_PUBLIC_ENABLED="true")
        output = inventory(db, flags, now=now)
        assert len(output) == 6
        first = output[0]
        assert first["key"] == "mikroton_tender"
        assert first["config_enabled"] is True
        assert first["sampled_stored_rows"] == 4
        assert first["recent_2h_rows"] == 3
        assert first["recent_2h_unexpired_previews"] == 1
        assert output[1]["config_enabled"] is True
        assert output[1]["sampled_stored_rows"] == 0
        assert all(row["sampled_stored_rows"] == 0 for row in output[1:])
    finally:
        db.close()


def test_unapproved_missing_flags_fail_closed():
    db = _db()
    try:
        with pytest.raises(ValueError, match="approval flag"):
            inventory(db, {}, now=datetime.now(timezone.utc))
        with pytest.raises(ValueError, match="approval flag"):
            inventory(db, _flags(MIKROTON_TENDER_ENABLED="unknown"),
                      now=datetime.now(timezone.utc))
        with pytest.raises(ValueError, match="UTC-aware"):
            inventory(db, _flags(), now=datetime(2026, 10, 28))
    finally:
        db.close()
