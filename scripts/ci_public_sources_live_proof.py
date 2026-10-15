"""Bounded, opt-in live evidence for VALYQON's eight default public adapters.

A green unit suite is not evidence of live acquisition.  A source only passes
this gate when its own adapter returns nonempty, validated notices from real
HTTPS at execution time. No user profile, credentials, database, AI or deployment
is used. These probes do NOT certify keyword recall, notice-detail links,
continuous operation, paid customer search or delivery to production.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any
from urllib.parse import urlsplit

DEFAULT_PUBLIC_SOURCES = (
    "ted", "uk_fts", "world_bank", "canada_buys",
    "austender", "nz_gets", "za_etenders", "india_cppp",
)
MAX_NOTICES = 3
PER_SOURCE_DEADLINE_SECONDS = 45
MAX_CONCURRENCY = 3


def source_factories(timeout: float = 12):
    """Only existing, anonymous, default-enabled official public sources."""
    from app.sources.ted_api import TedApiSource
    from app.sources.uk_fts_api import UkFindTenderApiSource
    from app.sources.world_bank import WorldBankSource
    from app.sources.canada_buys_dataset import CanadaBuysDatasetSource
    from app.sources.austender_rss import AusTenderRssSource
    from app.sources.nz_gets_rss import NzGetsRssSource
    from app.sources.za_etenders import ZaETendersSource
    from app.sources.india_cppp import IndiaCpppSource

    return {
        "ted": TedApiSource(timeout=timeout),
        "uk_fts": UkFindTenderApiSource(timeout=timeout),
        "world_bank": WorldBankSource(timeout=timeout),
        "canada_buys": CanadaBuysDatasetSource(timeout=timeout),
        "austender": AusTenderRssSource(timeout=timeout),
        "nz_gets": NzGetsRssSource(timeout=timeout),
        "za_etenders": ZaETendersSource(timeout=timeout),
        "india_cppp": IndiaCpppSource(timeout=timeout),
    }


def verify_notices(key: str, notices: Any) -> int:
    """Identity/URL validation, not an assertion of search coverage."""
    from app.sources.opportunities import validate_notice

    if type(notices) is not list or len(notices) > MAX_NOTICES:
        raise ValueError("unexpected adapter record collection")
    seen = set()
    for notice in notices:
        validate_notice(notice, key)
        parts = urlsplit(notice.url)
        if (parts.scheme != "https" or not parts.hostname or
                parts.username or parts.password or parts.fragment):
            raise ValueError("non-canonical notice URL")
        if notice.identity in seen:
            raise ValueError("duplicate notice identity")
        seen.add(notice.identity)
    return len(seen)


async def probe_one(key: str, adapter: Any, *, deadline: float = PER_SOURCE_DEADLINE_SECONDS):
    """Return only bounded aggregate metrics; never print source/secret contents."""
    try:
        notices = await asyncio.wait_for(adapter.fetch(limit=MAX_NOTICES), timeout=deadline)
        count = verify_notices(key, notices)
        return {"source": key,
                "status": "REAL_NOTICES_NORMALIZED" if count else "NO_VALID_NOTICES_IN_BATCH",
                "count": count}
    except asyncio.TimeoutError:
        return {"source": key, "status": "TIMEOUT", "count": 0}
    except Exception:
        # Exception messages can contain URLs, tokens, endpoint payloads or PII.
        return {"source": key, "status": "FETCH_OR_NORMALIZATION_FAILED", "count": 0}


async def live_proof():
    sources = source_factories()
    if tuple(sources) != DEFAULT_PUBLIC_SOURCES:
        raise ValueError("approved public source list changed")
    limit = asyncio.Semaphore(MAX_CONCURRENCY)

    async def limited_probe(key):
        async with limit:
            return await probe_one(key, sources[key])

    return await asyncio.gather(*(limited_probe(key) for key in DEFAULT_PUBLIC_SOURCES))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true",
                        help="Explicit public HTTPS check in isolated GitHub Actions only.")
    parser.add_argument("--require-all", action="store_true",
                        help="Fail closed unless every approved public adapter returned notices.")
    args = parser.parse_args(argv)

    if not args.live:
        print("SOURCE_LIVE_PROOF=NOT_RUN; EXTERNAL_HTTP=NO; NO_PRODUCTION_TOUCH=YES")
        return 0
    if (os.environ.get("GITHUB_ACTIONS") != "true" or
            os.environ.get("GITHUB_REPOSITORY") != "Ramzes2023/TenderLens-AI" or
            os.environ.get("GITHUB_EVENT_NAME") != "pull_request"):
        print("SOURCE_LIVE_PROOF=BLOCKED_NOT_ISOLATED_GITHUB_PR")
        return 2

    # Do not automatically load local dotenv or any credential configuration.
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    results = asyncio.run(live_proof())
    verified = sum(item["status"] == "REAL_NOTICES_NORMALIZED" for item in results)
    print(json.dumps({"source_live_proof": "PARTIAL_OR_COMPLETE",
                      "verified_now": verified,
                      "total_public_default_adapters": len(DEFAULT_PUBLIC_SOURCES),
                      "records_are_not_customer_deliveries": True,
                      "query_semantics_not_certified": True,
                      "results": results}, ensure_ascii=True, sort_keys=True))
    if args.require_all and verified != len(DEFAULT_PUBLIC_SOURCES):
        print("SOURCE_LIVE_PROOF=BLOCKED_NOT_ALL_SOURCES_VERIFIED")
        return 2
    print("SOURCE_LIVE_PROOF=PASS" if verified == len(DEFAULT_PUBLIC_SOURCES)
          else "SOURCE_LIVE_PROOF=PARTIAL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
