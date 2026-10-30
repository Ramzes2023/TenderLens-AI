"""Bounded EIS 44/223 public-feed acceptance FROM THE REVIEWED ISOLATED VPS WORKER.

Run only after the source Compose overlay is deployed. This script is
READ-ONLY: no SQL, no queue, no Telegram, no notices or secrets printed.
GitHub-hosted reachability is not equivalent to same-worker reachability.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from app.api.isolated_public_sources import ISOLATED_SQLITE_URL
from app.api.public_eis_identity import accepted_eis_original
from app.api.public_source_deadline import eligible_published_deadline

SOURCES = (("eis", "EIS_RSS_PUBLIC_ENABLED"), ("eis_223", "EIS_223_PUBLIC_ENABLED"))


def ready_notice(notice, key: str, now: datetime) -> bool:
    from dataclasses import asdict
    if getattr(notice, "source", None) != key:
        return False
    try:
        data = asdict(notice)
    except (TypeError, ValueError):
        return False
    return (accepted_eis_original(data)
            and eligible_published_deadline(key, data.get("deadline"), now=now))


async def inspect(catalog):
    now = datetime.now(timezone.utc)
    output = {}
    for name, _ in SOURCES:
        adapter = catalog.registry.get(name).source
        rows = await adapter.fetch(limit=8)
        accepted = sum(ready_notice(row, name, now) for row in rows)
        output[name] = {"retrieved": len(rows), "current_originals": accepted}
    return output


def main() -> int:
    if (os.environ.get("PYTHON_DOTENV_DISABLED") != "1"
            or os.environ.get("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED") != "true"
            or os.environ.get("DATABASE_URL") != ISOLATED_SQLITE_URL
            or os.environ.get("EIS_DIRECT_ENABLED") != "true"
            or any(os.environ.get(flag) != "true" for _, flag in SOURCES)
            or os.environ.get("TELEGRAM_BOT_TOKEN", "") != ""
            or os.environ.get("MONITORING_ENABLED") != "false"):
        print("EIS_VPS_ACCEPTANCE=BLOCKED_UNREVIEWED_CONTEXT")
        return 2
    from app.monitoring.config import load_monitoring_settings
    from app.sources.catalog import build_source_catalog
    try:
        catalog = build_source_catalog(load_monitoring_settings())
        if not all(name in catalog.enabled_keys for name, _ in SOURCES):
            raise ValueError("EIS sources not configured")
        counts = asyncio.run(inspect(catalog))
    except Exception as exc:
        # Only error TYPE. No upstream response, notice, URL, token or
        # customer data may leak from this trusted operator diagnostic.
        print("EIS_VPS_ACCEPTANCE=BLOCKED_SOURCE_OR_NETWORK")
        print("ERROR_CLASS=" + type(exc).__name__[:60])
        print("PRODUCTION_MODIFICATIONS=NONE")
        return 2
    for name, _ in SOURCES:
        print(name.upper() + "_FETCHED=" + str(counts[name]["retrieved"]))
        print(name.upper() + "_CURRENT_ORIGINALS=" + str(counts[name]["current_originals"]))
    ok = all(counts[name]["current_originals"] > 0 for name, _ in SOURCES)
    print("EIS_VPS_ACCEPTANCE=" + ("CANDIDATE_ONLY" if ok else "BLOCKED_NO_CURRENT_ORIGINALS"))
    print("WORKER_SQL_GUEST_HTTPS_AND_CADDY=NOT_VERIFIED_BY_THIS_PROBE")
    print("PRODUCTION_MODIFICATIONS=NONE")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
