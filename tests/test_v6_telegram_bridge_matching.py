"""No-send real-source snapshot and subscribed profile matching contracts."""
import json
import sqlite3
from datetime import datetime, timezone

import pytest

from app.monitoring.v6_bridge_matching import dry_run_paths, main
from tests.test_v6_telegram_bridge_readiness import seed, NOW


def build(tmp_path, *, keywords=("тестовой",)):
    sources = tmp_path / "sources.sqlite"
    customers = tmp_path / "customers.sqlite"
    profile = {
        "profile_version": "v1",
        "company_name": "Synthetic test-only company",
        "search_keywords": list(keywords),
        "product_keywords": [],
        "accepted_currencies": ["RUB"],
    }
    seed(sources, customers, profile=profile)
    # The shared preflight fixture intentionally models only the columns its
    # own aggregate audit uses. Exact V6 profile matching also validates the
    # real normalized notice identity from the source_opportunities PK column.
    # Add that missing column in THIS test's disposable database only.
    with sqlite3.connect(sources) as conn:
        conn.execute("ALTER TABLE source_opportunities ADD COLUMN external_id TEXT")
        conn.execute(
            "UPDATE source_opportunities SET external_id=? "
            "WHERE source_id='ru_samara_public_list'", ("12345678",)
        )
    return sources, customers


def test_matching_real_shaped_samara_notice_keeps_both_files_identical(tmp_path):
    a, b = build(tmp_path)
    original = a.read_bytes(), b.read_bytes()
    proof = dry_run_paths(a, b, now=NOW)
    assert proof["active_subscriptions"] == 1
    assert proof["fresh_open_validated_rows_considered"] == 1
    assert proof["unique_current_matching_notice_count"] == 1
    assert proof["subscriber_notice_pairs_after_seen_dedup"] == 1
    assert proof["matched_source_count"] == 1
    assert proof["live_telegram_send_authorized"] is False
    assert (a.read_bytes(), b.read_bytes()) == original


def test_no_keyword_match_means_no_telegram_candidate(tmp_path):
    a, b = build(tmp_path, keywords=("несуществующее",))
    proof = dry_run_paths(a, b, now=NOW)
    assert proof["unique_current_matching_notice_count"] == 0
    assert proof["subscriptions_with_unsent_matching_rows"] == 0


def test_seen_journal_suppresses_original_for_the_same_subscriber(tmp_path):
    a, b = build(tmp_path)
    with sqlite3.connect(b) as db:
        db.execute(
            "INSERT INTO monitor_seen VALUES (?,?,?)",
            (10001, "ru_samara_public_list", "12345678"),
        )
    result = dry_run_paths(a, b, now=NOW)
    assert result["subscriber_notice_pairs_after_seen_dedup"] == 0


def test_corrupted_stored_identity_is_not_matched(tmp_path):
    a, b = build(tmp_path)
    with sqlite3.connect(a) as db:
        row = db.execute("SELECT notice_json FROM source_opportunities").fetchone()
        bad = json.loads(row[0])
        bad["external_id"] = "untrusted-mismatch"
        db.execute("UPDATE source_opportunities SET notice_json=?", (json.dumps(bad),))
    # A tampered first-party ID invalidates the mandatory readiness gate.
    # Refuse the entire run rather than silently treating corrupt identity
    # as a legitimate zero-match source snapshot.
    with pytest.raises(ValueError, match="Failed source or subscription readiness gate"):
        dry_run_paths(a, b, now=NOW)


def test_missing_explicit_keywords_block_all_candidates(tmp_path):
    a, b = build(tmp_path, keywords=())
    with pytest.raises(ValueError):
        dry_run_paths(a, b, now=NOW)


def test_same_database_blocked(tmp_path):
    a, _ = build(tmp_path)
    with pytest.raises(ValueError):
        dry_run_paths(a, a, now=NOW)


def test_cli_does_not_print_title_keyword_or_recipient(tmp_path, capsys):
    a, b = build(tmp_path, keywords=("private-test-only-keyword",))
    code = main(["--sources-db", str(a), "--customer-db", str(b)])
    text = capsys.readouterr().out
    assert code in (0, 2)
    for secret in ("private-test-only-keyword", "Synthetic test-only", "10001", "12345678",
                   "Реальный формат тестовой закупки"):
        assert secret not in text
    assert "TELEGRAM_SEND_AUTHORIZED=NO" in text
    assert "PRODUCTION_MODIFICATIONS=NONE" in text
