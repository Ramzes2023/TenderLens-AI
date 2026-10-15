"""Bounded, read-only public notice acquisition into an ephemeral test DB.

Runs in GitHub Actions on an unprivileged runner. Never touches production,
does not authenticate, follow redirects, bypass CAPTCHA, or disable TLS.
A passing process exit only means the *diagnostic ran*: results may be BLOCKED.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch
import json
import os
import tempfile
from pathlib import Path

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources import eis_rss, eis_223_rss, b2b_center
from app.sources.eis_rss import build_eis_rss_url
from app.sources.eis_223_rss import build_eis_223_rss_url
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog


SOURCE_KEYS = ("eis", "eis_223", "b2b_center")
MAX_RECORDS = 10
REQUEST_TIMEOUT = 15
TOTAL_FETCH_TIMEOUT = 25


def _settings():
    return MonitoringSettings(
        enabled=False,
        interval_seconds=600,
        max_items=MAX_RECORDS,
        max_notifications_per_cycle=5,
        request_timeout=REQUEST_TIMEOUT,
        eis_rss_urls=(build_eis_rss_url("поставка"),),
        ca_bundle_file=None,
        profile_feeds_enabled=False,
        eis_223_enabled=True,
        eis_223_rss_urls=(build_eis_223_rss_url("поставка"),),
        eis_223_profile_feeds_enabled=False,
        b2b_center_enabled=True,
        eis_direct_enabled=True,
        eis_system_trust_enabled=(os.name == "nt"),  # Windows: strict system CA store.
    )


async def _fetch(key, source, entry):
    # Observe only the HTTP status exposed through the existing bounded,
    # public-IP-validated transport. Never log URL, response body or headers.
    module = {"eis": eis_rss, "eis_223": eis_223_rss,
              "b2b_center": b2b_center}[key]
    original = module.source_client

    @asynccontextmanager
    async def observed_client(**kwargs):
        hooks = kwargs.get("event_hooks") or {}
        async def record(response):
            entry["http_status"] = response.status_code
        kwargs["event_hooks"] = {
            **hooks, "response": [*(hooks.get("response") or []), record],
        }
        async with original(**kwargs) as client:
            yield client

    with patch.object(module, "source_client", observed_client):
        return await asyncio.wait_for(source.fetch(MAX_RECORDS),
                                      timeout=TOTAL_FETCH_TIMEOUT)


def main():
    result = {}
    with tempfile.TemporaryDirectory(prefix="valyqon-ru-public-") as temporary:
        db = Database(DatabaseSettings("ru-gh-live-ephemeral", Path(temporary) / "notices.sqlite"))
        try:
            repo = OpportunityRepository(db)
            repo.initialize()
            catalog = build_source_catalog(_settings())
            snapshot = snapshot_catalog(catalog, repo)

            for key in SOURCE_KEYS:
                entry = result[key] = {
                    "state": "BLOCKED", "records": 0, "db": 0, "query": 0,
                    "error_type": None, "http_status": None,
                }
                try:
                    adapter = catalog.registry.get(key).source
                    notices = asyncio.run(_fetch(key, adapter, entry))
                    if not notices:
                        entry.update(state="EMPTY_NOT_VERIFIED")
                        continue
                    entry["records"] = len(notices)
                    for notice in notices:
                        if notice.source != key:
                            raise ValueError("Connector identity mismatch")
                        repo.upsert(notice, f"connector-sync-v1:{key}:adapter-r1")
                        entry["db"] += 1

                    for notice in notices:
                        report = asyncio.run(snapshot.fetch(
                            source_keys=(key,),
                            search_terms=(notice.external_id,),
                            limit_per_source=MAX_RECORDS,
                        ))
                        if not report.failures and any(
                            row.identity == notice.identity and row.url == notice.url
                            for row in report.notices
                        ):
                            entry["query"] += 1
                    if entry["db"] == entry["query"] == entry["records"]:
                        entry["state"] = "PUBLIC_FETCH_SQLITE_KEYWORD_VERIFIED"
                    else:
                        entry["state"] = "INCOMPLETE_DB_OR_KEYWORD_QUERY"
                except Exception as error:
                    # Do not print URLs, body content, credentials or exception messages.
                    entry["error_type"] = type(error).__name__
                    entry["state"] = "BLOCKED"
        finally:
            db.close()
    count = sum(
        entry["state"] == "PUBLIC_FETCH_SQLITE_KEYWORD_VERIFIED"
        for entry in result.values()
    )
    print("RU_GITHUB_PUBLIC_NETWORK_EVIDENCE=" + json.dumps(
        result, ensure_ascii=False, separators=(",", ":")
    ), flush=True)
    print(f"RU_GITHUB_PUBLIC_FETCH_SQLITE_QUERY_VERIFIED={count}/3", flush=True)
    print("AUTHENTICATED_AI_SEARCH_VERIFIED=NO", flush=True)
    print("NOTICE_DETAIL_IDENTITY_VERIFIED=NO", flush=True)
    windows_ca_verified = (os.name == "nt" and all(
        result[key]["state"] == "PUBLIC_FETCH_SQLITE_KEYWORD_VERIFIED"
        for key in ("eis", "eis_223")
    ))
    print("WINDOWS_TRUSTED_CA_VERIFIED_BY_THIS_RUN=" +
          ("YES" if windows_ca_verified else "NO"), flush=True)
    print("PRODUCTION_CHANGED=NO", flush=True)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as target:
            target.write("\n### Russian public source smoke (observational only)\n\n")
            target.write("| Source | Result | Retrieved | Stored | Keyword query |\n")
            target.write("| --- | --- | ---: | ---: | ---: |\n")
            for key, row in result.items():
                target.write(f"| `{key}` | {row['state']} | {row['records']} | "
                             f"{row['db']} | {row['query']} |\n")
            target.write("\nThis job uses ephemeral SQLite and public endpoints only. "
                         "It does not verify individual detail pages, authenticated AI "
                         "search, Windows TLS, or production enablement. "
                         "A successful diagnostic step does **not** imply three live "
                         "integrations are ready.\n")

    # A blocked source should be observable, not falsely reported as live.
    # This diagnostic never gates the offline test suite because GitHub's
    # geography/network may differ from the real Windows deployment host.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
