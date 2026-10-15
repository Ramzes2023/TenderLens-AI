"""Fail-closed live acceptance for six official Asian public procurement feeds.

Read-only anonymous source fetches; isolated SQLite; identity/lookup round-trip.
No deployment, credentials, tenant data or publication to the SaaS.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.monitoring.config import MonitoringSettings
from app.sources.asia_public import ASIA_RSS_FEEDS, JETRO_LISTS
from app.sources.catalog import build_source_catalog
from app.sources.opportunities import OpportunityRepository, validate_notice
from app.sources.snapshots import snapshot_catalog

KEYS = (*ASIA_RSS_FEEDS, *JETRO_LISTS)


def settings():
    return MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=10,
        max_notifications_per_cycle=5, request_timeout=25.0,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        profile_feed_limit=5,
    )


async def fetch_one(source):
    return await asyncio.wait_for(source.fetch(5), timeout=40)


def main():
    os.environ["VALYQON_ASIA_SOURCES_ENABLED"] = "1"
    summary = {}
    with tempfile.TemporaryDirectory(prefix="valyqon-asia-six-") as temp:
        database = Database(DatabaseSettings("asia-gh-ephemeral", Path(temp) / "notices.sqlite"))
        try:
            opportunities = OpportunityRepository(database)
            opportunities.initialize()
            catalog = build_source_catalog(settings())
            snapshot = snapshot_catalog(catalog, opportunities)
            for key in KEYS:
                item = {"live": "BLOCKED", "fetched": 0, "stored": 0, "queried": 0}
                summary[key] = item
                try:
                    source = catalog.registry.get(key).source
                    notices = asyncio.run(fetch_one(source))
                    item["fetched"] = len(notices)
                    if not notices:
                        item["live"] = "NO_RECORDS"
                        continue
                    for notice in notices:
                        validate_notice(notice, key)
                        opportunities.upsert(notice, f"connector-sync-v1:{key}:adapter-r1")
                        item["stored"] += 1
                    for notice in notices:
                        report = asyncio.run(snapshot.fetch(
                            source_keys=(key,), search_terms=(notice.external_id,), limit_per_source=10,
                        ))
                        if not report.failures and any(
                            hit.identity == notice.identity and hit.url == notice.url
                            for hit in report.notices
                        ):
                            item["queried"] += 1
                    if item["fetched"] == item["stored"] == item["queried"]:
                        item["live"] = "FETCH_SQLITE_SEARCH_VERIFIED"
                    else:
                        item["live"] = "INCOMPLETE"
                except Exception as exc:
                    # Never dump scraped document bodies, client URLs or secrets.
                    item["error_type"] = type(exc).__name__
                    # SourceError messages are fixed, public, code-owned messages
                    # without response bodies, URLs, credentials or query strings.
                    from app.sources.eis_rss import SourceError
                    if isinstance(exc, SourceError):
                        item["reason"] = str(exc)
                    item["live"] = "BLOCKED"
        finally:
            database.close()
    successes = sum(x["live"] == "FETCH_SQLITE_SEARCH_VERIFIED" for x in summary.values())
    print("ASIA_SIX_SOURCE_LIVE_RESULTS=" + json.dumps(summary, sort_keys=True))
    print(f"ASIA_SIX_SOURCE_FETCH_SQLITE_QUERY_VERIFIED={successes}/6")
    print("PRODUCTION_CHANGED=NO")
    print("AUTO_MERGE=NO")
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as out:
            out.write("\n### Asian source live proof — anonymous GitHub runner\n\n")
            out.write("| Source | Result | Fetched | Stored | Queried |\n| --- | --- | ---: | ---: | ---: |\n")
            for key, item in summary.items():
                out.write(f"| {key} | {item['live']} | {item['fetched']} | {item['stored']} | {item['queried']} |\n")
            out.write("\nThis is a GitHub-runner observation, not proof of AWS reachability or a production deployment.\n")
    return 0 if successes == len(KEYS) else 3


if __name__ == "__main__":
    raise SystemExit(main())
