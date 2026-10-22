"""Read-only Ingushetia Worker snapshot observation, never a delivery attestation.

No live source requests, Telegram API, queue enqueue, user profiles, secret
values or migrations. A fresh SQL last_seen only proves recent local persistence;
it does NOT prove present-tense upstream availability, current publication,
real Bot API delivery, or production readiness.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json

from app.sources.snapshots import INGUSHETIA_WORKER_MAX_AGE_SECONDS

SOURCES = ("ru_ingushetia_eis44", "ru_ingushetia_fabrikant44")


def snapshot_health(settings, repository, *, now=None):
    """Conservatively classify each *operator-enabled* regional SQL snapshot."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("UTC-aware observation clock required")

    flags = {
        "background_monitor_enabled": bool(settings.enabled),
        "ru_catalog_enabled": bool(settings.ru_background_catalog_enabled),
        "worker_sql_alerts_enabled": bool(settings.ru_ingushetia_worker_sql_alerts_enabled),
    }
    allowed = (
        "ru_ingushetia_eis44" if settings.ru_ingushetia_eis44_enabled else None,
        "ru_ingushetia_fabrikant44" if settings.ru_ingushetia_fabrikant44_enabled else None,
    )
    active = tuple(k for k in allowed if k)
    # Independently count even when scheduling/Telegram is disabled. The output
    # remains observational and never turns source flags on.
    sources = {}
    lower = now - timedelta(seconds=INGUSHETIA_WORKER_MAX_AGE_SECONDS)
    for source in active:
        try:
            seen = repository.latest_seen_utc(source)
            if seen is None:
                state = "SQL_ABSENT"
            elif seen.tzinfo is None or seen.utcoffset() != timedelta(0):
                state = "SQL_TIMESTAMP_INVALID"
            elif seen > now + timedelta(seconds=120):
                state = "SQL_CLOCK_SKEW"
            elif seen < lower:
                state = "SQL_STALE"
            else:
                # A single recent row must not imply that other historic
                # notices were refreshed or can be sent to users.
                rows = repository.read(source, limit=100, search_terms=(), not_before=lower)
                state = "RECENT_SQL_OBSERVED" if rows else "SQL_EMPTY"
        except Exception:
            # Underlying errors can include database URLs and credentials.
            # Fail closed without disclosing raw exception text or type.
            state = "SQL_UNAVAILABLE"
        sources[source] = state

    configured = bool(active) and all(flags.values())
    current = configured and all(x == "RECENT_SQL_OBSERVED" for x in sources.values())
    return {
        "observation": "INGUSHETIA_READ_ONLY_SNAPSHOT",
        "status": "SQL_SNAPSHOT_OBSERVED_ONLY" if current else "NOT_OPERATIONALLY_READY",
        "flags": flags,
        "source_states": sources,
        "source_enabled_count": len(active),
        "telegram_bot_api_receipt_proven": False,
        "current_upstream_reachability_proven": False,
        "production_changed": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect-only", action="store_true",
                        help="Explicit read-only status, not activation or delivery")
    args = parser.parse_args(argv)
    if not args.inspect_only:
        print("INGUSHETIA_RUNTIME_STATUS=BLOCKED; EXPLICIT_READ_ONLY_FLAG_REQUIRED=YES")
        return 2

    database = None
    try:
        from app.monitoring.config import load_monitoring_settings
        from app.database.config import load_database_settings
        from app.database.backend import Database
        from app.sources.opportunities import OpportunityRepository

        settings = load_monitoring_settings()
        config = load_database_settings()
        # sqlite3.connect() creates a missing file; avoid even that
        # side-effect in a command that promises read-only observation.
        if config.backend == "sqlite" and (
            config.path is None or not config.path.is_file()
        ):
            raise ValueError("Snapshot database is absent")
        database = Database(config)
        report = snapshot_health(settings, OpportunityRepository(database))
        print("INGUSHETIA_RUNTIME_STATUS=" + json.dumps(report, sort_keys=True))
        return 0 if report["status"] == "SQL_SNAPSHOT_OBSERVED_ONLY" else 2
    except Exception:
        print("INGUSHETIA_RUNTIME_STATUS=BLOCKED; SAFE_DATABASE_OR_CONFIG_REVIEW_REQUIRED=YES")
        return 2
    finally:
        if database is not None:
            database.close()


if __name__ == "__main__":
    raise SystemExit(main())
