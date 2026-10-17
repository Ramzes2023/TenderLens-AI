"""Operator-only ALL verified Asian sources: queue and persistent keyword search.

No network request, tenant mutation or scheduling from this command; the
existing opt-in --connectors Worker performs bounded upstream fetches.
Never silently mark a queued, failed or stale job as delivered to customers.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone

from .asia_public import ASIA_RSS_FEEDS
from .hk_hyd_tenders import SOURCE_ID as HK_HYD
from .jp_jetro_bid_rss import SOURCE_ID as JP_JETRO
from .hk_hkma_tender import SOURCE_ID as HK_HKMA
from .india_epublish import SOURCE_ID as INDIA_EPUBLISH
from .uae_mof_rfqs import SOURCE_ID as UAE_MOF
from .sg_gebiz_rss import FEEDS as SG_GEBIZ
from .ingestion import validate_payload, connector_version, sync_window

SOURCES = (*ASIA_RSS_FEEDS, JP_JETRO, HK_HYD, *SG_GEBIZ, HK_HKMA, INDIA_EPUBLISH, UAE_MOF)
FLAGS = {
    **{key: "VALYQON_ASIA_SOURCES_ENABLED" for key in ASIA_RSS_FEEDS},
    JP_JETRO: "VALYQON_ASIA_JETRO_BID_ENABLED",
    HK_HYD: "VALYQON_ASIA_HYD_ENABLED",
    HK_HKMA: "VALYQON_ASIA_HKMA_ENABLED",
    INDIA_EPUBLISH: "VALYQON_ASIA_INDIA_EPUBLISH_ENABLED",
    UAE_MOF: "VALYQON_ASIA_UAE_FEDERAL_ENABLED",
    **{key: "VALYQON_ASIA_GEBIZ_ENABLED" for key in SG_GEBIZ},
}
MAX_RETURNED = 30
_QUERY = re.compile(r"^[^\x00-\x1f\x7f]{2,120}$")
assert len(SOURCES) == len(set(SOURCES)) == len(FLAGS) == 13


def validate_batch(catalog, *, sources=SOURCES, now=None):
    """All sources must pass registration + flag gates before opening DB."""
    if not sources or len(set(sources)) != len(sources) or any(key not in FLAGS for key in sources):
        raise ValueError("Invalid approved Asian source selection.")
    window = sync_window(now)
    for key in sources:
        if os.environ.get(FLAGS[key], "").strip() != "1":
            raise ValueError("Asian source is not explicitly activated.")
        validate_payload({
            "schema": 1,
            "source_id": key,
            "sync_window": window,
            "connector_version": connector_version(key),
        }, catalog.registry)
    return tuple(sources)


def stored_search(store, query, *, source=None, limit=20):
    """No HTTPS; only public notices already stored via fenced worker jobs."""
    if (not isinstance(query, str)
            or any(ord(c) < 32 or ord(c) == 127 for c in query)
            or not _QUERY.fullmatch(query.strip())):
        raise ValueError("Invalid printable keyword.")
    if type(limit) is not int or not 1 <= limit <= MAX_RETURNED:
        raise ValueError("Invalid maximum result count.")
    if source is not None and source not in SOURCES:
        raise ValueError("Unapproved Asian source.")
    results=[]
    for key in (SOURCES if source is None else (source,)):
        for tender in store.read(key, limit=limit, search_terms=(query.strip(),)):
            results.append({
                "source": tender.source,
                "external_id": tender.external_id,
                "title": tender.title,
                "url": tender.url,
                "customer": tender.customer,
                "published_at": tender.published_at,
                "deadline": tender.deadline,
                "region": tender.region,
                "currency": tender.currency,
                "initial_price": tender.initial_price,
            })
    results.sort(key=lambda row: (
        row["published_at"] or "", row["source"], row["external_id"]
    ), reverse=True)
    return results[:limit]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument("--enqueue", action="store_true",
                      help="Idempotently queue approved Asian sources for current UTC hour.")
    mode.add_argument("--search", metavar="KEYWORD", help="Search durable locally stored Asian tenders.")
    parser.add_argument("--source", choices=SOURCES, help="Explicit one-source enqueue/search.")
    parser.add_argument("--limit", type=int, default=20, help="Max returned keyword results 1..30")
    args=parser.parse_args(argv)

    if not args.enqueue and args.search is None:
        print(json.dumps({
            "mode": "dry_run",
            "sources": list(SOURCES),
            "total_sources": len(SOURCES),
            "enqueued": 0,
            "production_changed": False,
            "requires_explicit_activation": sorted(set(FLAGS.values())),
        }, separators=(",", ":")))
        return 0

    db=None
    try:
        if os.environ.get("VALYQON_ASIA_OPERATIONS_ENABLED", "").strip() != "1":
            raise ValueError("Explicit trusted operator activation required.")
        if args.enqueue:
            from app.monitoring.config import load_monitoring_settings
            from app.database.backend import Database
            from app.database.config import load_database_settings
            from app.jobs import JobRepository, JobService, load_job_settings
            from .catalog import build_source_catalog
            from .ingestion import ConnectorSyncService

            selected=(args.source,) if args.source else SOURCES
            catalog=build_source_catalog(load_monitoring_settings())
            instant=datetime.now(timezone.utc)
            verified=validate_batch(catalog, sources=selected, now=instant)
            db=Database(load_database_settings())
            jobs=JobRepository(db, load_job_settings())
            jobs.initialize()
            service=ConnectorSyncService(JobService(jobs), catalog)
            output=[]
            for key in verified:
                job=service.enqueue(key, now=instant)
                output.append({"source":key,"job_id":job.id,"state":job.state})
            print(json.dumps({"mode":"queued","source_count":len(output),"jobs":output,
                              "requires_running_connector_worker":True},
                             ensure_ascii=False,separators=(",", ":")))
            return 0

        # All keyword searches are local; never disclose customer profile terms
        # upstream or open any network connection.
        if args.search is None or not _QUERY.fullmatch(args.search.strip()) or (
                any(ord(x) < 32 or ord(x) == 127 for x in args.search)):
            raise ValueError("Invalid search input.")
        from app.database.backend import Database
        from app.database.config import load_database_settings
        from .opportunities import OpportunityRepository
        db=Database(load_database_settings())
        rows=stored_search(OpportunityRepository(db),args.search,source=args.source,limit=args.limit)
        print(json.dumps({"mode":"stored_search","query":args.search.strip(),
                          "results":rows,"count":len(rows),
                          "network_fetch":False,"only_previously_ingested":True},
                         ensure_ascii=False,separators=(",", ":")))
        return 0
    except Exception:
        print("Asian source operation blocked or failed; verify source flags and trusted infrastructure.")
        return 2
    finally:
        if db is not None:
            db.close()


if __name__=="__main__":
    raise SystemExit(main())
