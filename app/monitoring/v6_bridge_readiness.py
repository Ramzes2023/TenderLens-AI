"""Read-only readiness gate for isolated V6 -> subscribed Telegram bridge.

This is NOT a sender and does not authorize starting a bot. Neither database is
opened for writing; no token, chat, owner, company, title or keyword is printed.
Operator must mount the TWO independent existing volumes read-only.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from app.api.public_source_deadline import eligible_published_deadline

SOURCES = (
    "mikroton_tender",
    "stan_commercial_public",
    "south_ural_public",
    "kavkaz_rf_firstparty",
    "lenobl_small_public",
    "ru_samara_public_list",
)
SAMARA_GRID = "https://webtorgi.samregion.ru/smallpurchases/GzwSP/NoticesGrid"
MAX_AGE_SECONDS = 7200


def _timestamp(raw):
    if not isinstance(raw, str):
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return None
    return value.astimezone(timezone.utc) if value.tzinfo else None


def _recent(raw, now):
    value = _timestamp(raw)
    return value is not None and 0 <= (now - value).total_seconds() <= MAX_AGE_SECONDS


def _connect_readonly(path):
    file = Path(path)
    if not file.is_file() or file.is_symlink():
        raise ValueError("Existing regular database required")
    uri = "file:" + quote(str(file.resolve()), safe="/") + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    connection.execute("PRAGMA query_only=ON")
    return connection


def _has_tables(db, names):
    existing = {row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    return set(names).issubset(existing)


def _keywords(profile_json):
    try:
        profile = json.loads(profile_json)
    except (ValueError, TypeError):
        return False
    if not isinstance(profile, dict):
        return False
    # Do not silently fall back to an unrestricted profile or global default.
    for field in ("search_keywords", "product_keywords"):
        words = profile.get(field, [])
        if not isinstance(words, list):
            return False
        if any(not isinstance(word, str) or not word.strip() for word in words):
            return False
        if any(len(word.strip()) > 200 for word in words):
            return False
    return bool(profile.get("search_keywords") or profile.get("product_keywords"))


def audit_connections(source_db, customer_db, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("UTC-aware time required")
    now = now.astimezone(timezone.utc)
    if not _has_tables(source_db, ("source_opportunities", "durable_jobs")):
        raise ValueError("V6 source schema missing")
    if not _has_tables(customer_db, (
        "monitor_subscriptions", "monitor_seen", "company_active", "company_workspaces"
    )):
        raise ValueError("Customer monitoring schema missing")
    if source_db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise ValueError("Source database integrity check failed")
    if customer_db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise ValueError("Customer database integrity check failed")

    rows = source_db.execute(
        "SELECT payload_json,state,result_json,finished_at FROM durable_jobs "
        "WHERE job_type='connector.sync.v1' ORDER BY created_at DESC LIMIT 600"
    ).fetchall()
    latest = {}
    for raw, state, raw_result, finished in rows:
        try:
            payload = json.loads(raw)
            source = payload.get("source_id") if isinstance(payload, dict) else None
            if source not in SOURCES or source in latest:
                continue
            evidence = json.loads(raw_result) if raw_result else {}
            accepted = evidence.get("accepted_count") if isinstance(evidence, dict) else None
            latest[source] = (state == "succeeded" and _recent(finished, now)
                              and type(accepted) is int and accepted >= 0)
        except (ValueError, TypeError, AttributeError):
            continue

    current = {source: 0 for source in SOURCES}
    for source in SOURCES:
        observations = source_db.execute(
            "SELECT notice_json,last_seen FROM source_opportunities "
            "WHERE source_id=? ORDER BY last_seen DESC LIMIT 200", (source,)
        ).fetchall()
        for raw, last_seen in observations:
            if not _recent(last_seen, now):
                continue
            try:
                notice = json.loads(raw)
                if (not isinstance(notice, dict)
                        or notice.get("source") != source
                        or not isinstance(notice.get("title"), str)
                        or not notice["title"].strip()
                        or not eligible_published_deadline(
                            source, notice.get("deadline"), now=now)):
                    continue
                if source == "ru_samara_public_list" and (
                    notice.get("url") != SAMARA_GRID or
                    not isinstance(notice.get("external_id"), str) or
                    re.fullmatch(r"[0-9]{6,12}", notice["external_id"]) is None
                ):
                    continue
                current[source] += 1
            except (TypeError, ValueError, OverflowError):
                continue

    profiles = customer_db.execute(
        "SELECT w.profile_json FROM monitor_subscriptions AS m "
        "LEFT JOIN company_active AS a ON a.owner_user_id=m.owner_user_id "
        "LEFT JOIN company_workspaces AS w "
        "ON w.owner_user_id=m.owner_user_id AND w.id=a.company_id "
        "WHERE m.enabled=1"
    ).fetchall()
    subscribed = len(profiles)
    explicit_profiles = sum(1 for (profile_json,) in profiles if _keywords(profile_json))
    eligible = (subscribed > 0 and subscribed == explicit_profiles
                and all(latest.get(source, False) for source in SOURCES)
                and current["ru_samara_public_list"] > 0)

    return {
        "scope": "two_isolated_databases_readonly",
        "approved_sources": len(SOURCES),
        "recent_successful_workers": sum(bool(latest.get(source)) for source in SOURCES),
        "safely_current_source_rows": sum(current.values()),
        "safely_current_samara_list_rows": current["ru_samara_public_list"],
        "active_subscriptions": subscribed,
        "subscriptions_with_explicit_active_company_keywords": explicit_profiles,
        "read_only_candidate": bool(eligible),
        "telegram_live_send_authorized": False,
        "telegram_delivery_confirmed": False,
        "profile_contents_exposed": False,
        "user_identifiers_exposed": False,
        "database_writes": False,
    }


def audit_paths(source_path, customer_path, *, now=None):
    if Path(source_path).resolve() == Path(customer_path).resolve():
        raise ValueError("Customer and source databases must remain isolated")
    with closing(_connect_readonly(source_path)) as sources:
        with closing(_connect_readonly(customer_path)) as customers:
            return audit_connections(sources, customers, now=now)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources-db", required=True, type=Path)
    parser.add_argument("--customer-db", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = audit_paths(args.sources_db, args.customer_db)
    except (OSError, ValueError, sqlite3.Error):
        print("V6_TELEGRAM_BRIDGE_READONLY=BLOCKED")
        print("TELEGRAM_LIVE_SEND_AUTHORIZED=NO")
        print("PRODUCTION_MODIFICATIONS=NONE")
        return 2
    print("V6_TELEGRAM_BRIDGE_AUDIT=" + json.dumps(result, sort_keys=True))
    print("V6_TELEGRAM_BRIDGE_READONLY=" + (
        "CANDIDATE_ONLY" if result["read_only_candidate"] else "BLOCKED_PRECONDITIONS"))
    print("TELEGRAM_LIVE_SEND_AUTHORIZED=NO")
    print("PRODUCTION_MODIFICATIONS=NONE")
    return 0 if result["read_only_candidate"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
