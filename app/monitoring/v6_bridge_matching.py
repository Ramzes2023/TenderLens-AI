"""No-send V6 live-notice -> existing Telegram subscriber profile comparison.

Two separate SQLite DBs are read-only; NEVER sends Telegram, claims seen or
prints buyer/title/profile/owner/chat identifiers. This is not notification
consent or production delivery acceptance.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from dataclasses import fields
from datetime import datetime, timezone

from app.api.public_source_deadline import eligible_published_deadline
from app.monitoring.service import prefilter_notice
from app.scoring.models import CompanyProfile
from app.sources.models import TenderNotice
from app.sources.opportunities import validate_notice
from .v6_bridge_readiness import (
    SOURCES, SAMARA_GRID, _connect_readonly, _recent, audit_connections,
)

MAX_ROWS_PER_SOURCE = 200
MAX_SUBSCRIBERS = 100
_NOTICE_FIELDS = frozenset(item.name for item in fields(TenderNotice))


def _validated_notice(raw, source, external_id, now):
    try:
        data = json.loads(raw)
        if (not isinstance(data, dict)
                or data.get("source") != source
                or not isinstance(external_id, str)
                or not external_id
                or data.get("external_id") != external_id
                or not eligible_published_deadline(source, data.get("deadline"), now=now)):
            return None
        if source == "ru_samara_public_list" and data.get("url") != SAMARA_GRID:
            return None
        notice = TenderNotice(**{key: data[key] for key in _NOTICE_FIELDS if key in data})
        validate_notice(notice, source)
        return notice
    except (ValueError, TypeError, OverflowError, KeyError):
        return None


def _subscriptions(customer_db):
    rows = customer_db.execute(
        "SELECT m.owner_user_id, w.profile_json "
        "FROM monitor_subscriptions AS m "
        "LEFT JOIN company_active AS a ON a.owner_user_id=m.owner_user_id "
        "LEFT JOIN company_workspaces AS w "
        "ON w.owner_user_id=m.owner_user_id AND w.id=a.company_id "
        "WHERE m.enabled=1 ORDER BY m.owner_user_id LIMIT ?",
        (MAX_SUBSCRIBERS + 1,),
    ).fetchall()
    if not rows or len(rows) > MAX_SUBSCRIBERS:
        raise ValueError("Missing or unbounded subscription population")
    profiles = []
    for owner, raw in rows:
        try:
            profile = CompanyProfile.model_validate_json(raw)
        except (ValueError, TypeError):
            raise ValueError("Invalid active company profile") from None
        if not profile.monitoring_keywords:
            raise ValueError("Unrestricted subscriber profile prohibited")
        if not all(isinstance(term, str) and term.strip() for term in profile.monitoring_keywords):
            raise ValueError("Invalid monitoring keywords")
        profiles.append((owner, profile))
    return profiles


def dry_run_connections(source_db, customer_db, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("UTC-aware current time required")
    now = now.astimezone(timezone.utc)
    baseline = audit_connections(source_db, customer_db, now=now)
    if not baseline["read_only_candidate"]:
        raise ValueError("Failed source or subscription readiness gate")
    subscribers = _subscriptions(customer_db)
    matched_identity = set()
    matches_by_source = {key: 0 for key in SOURCES}
    subscriber_matched = set()
    scanned = 0
    for source in SOURCES:
        rows = source_db.execute(
            "SELECT external_id,notice_json,last_seen FROM source_opportunities "
            "WHERE source_id=? ORDER BY last_seen DESC LIMIT ?",
            (source, MAX_ROWS_PER_SOURCE),
        ).fetchall()
        for identity, raw, stamp in rows:
            if not _recent(stamp, now):
                continue
            notice = _validated_notice(raw, source, identity, now)
            if notice is None:
                continue
            scanned += 1
            for owner, profile in subscribers:
                if prefilter_notice(notice, profile) is None:
                    continue
                # Hard rule: the profile must actually match a notice text
                # keyword; fallback or soft non-match is not a recipient match.
                from app.monitoring.service import _term_match
                haystack = " ".join(filter(None, (notice.title, notice.summary)))
                if not any(_term_match(haystack, word) for word in profile.monitoring_keywords):
                    continue
                # Existing private dedup journal: never re-notify a notice
                # previously marked seen for this particular subscriber.
                already_seen = customer_db.execute(
                    "SELECT 1 FROM monitor_seen "
                    "WHERE owner_user_id=? AND source=? AND external_id=? LIMIT 1",
                    (owner, source, identity),
                ).fetchone()
                if already_seen:
                    continue
                matched_identity.add((source, identity))
                matches_by_source[source] += 1
                subscriber_matched.add(owner)
    return {
        "scope": "existing_explicit_subscription_profile_match_readonly",
        "six_sources_fresh_worker_verified": baseline["recent_successful_workers"] == 6,
        "fresh_open_validated_rows_considered": scanned,
        "active_subscriptions": len(subscribers),
        "subscriptions_with_unsent_matching_rows": len(subscriber_matched),
        "unique_current_matching_notice_count": len(matched_identity),
        "subscriber_notice_pairs_after_seen_dedup": sum(matches_by_source.values()),
        "matched_source_count": sum(1 for x in matches_by_source.values() if x),
        "live_telegram_send_authorized": False,
        "live_telegram_delivery_verified": False,
        "source_database_modified": False,
        "customer_database_modified": False,
        "source_names_titles_keywords_and_recipient_ids_printed": False,
    }


def dry_run_paths(source_path, customer_path, *, now=None):
    from pathlib import Path
    if Path(source_path).resolve() == Path(customer_path).resolve():
        raise ValueError("Source and customer stores must remain isolated")
    with closing(_connect_readonly(source_path)) as source:
        with closing(_connect_readonly(customer_path)) as customer:
            return dry_run_connections(source, customer, now=now)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources-db", required=True)
    parser.add_argument("--customer-db", required=True)
    args = parser.parse_args(argv)
    try:
        result = dry_run_paths(args.sources_db, args.customer_db)
    except (OSError, ValueError, sqlite3.Error):
        print("V6_TELEGRAM_PROFILE_DRYRUN=BLOCKED")
        print("TELEGRAM_SEND_AUTHORIZED=NO")
        print("PRODUCTION_MODIFICATIONS=NONE")
        return 2
    print("V6_TELEGRAM_PROFILE_DRYRUN=" + json.dumps(result, sort_keys=True))
    print("TELEGRAM_SEND_AUTHORIZED=NO")
    print("PRODUCTION_MODIFICATIONS=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
