"""Bounded live polls on real adapters; cumulative original IDs, no Telegram.

Uses public network reads only, never production. First successful poll per source is
a baseline, not newly published notices. Later unseen IDs mean first observed
in this audit, not proof of their upstream publication time. No archived IDs.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import json
import time

from app.sources.ru_notice_identity import original_notice_key
from app.sources.ru_ingushetia_eis44 import SOURCE_ID as EIS
from app.sources.ru_ingushetia_fabrikant44 import SOURCE_ID as FAB
from scripts.ci_ru_ingushetia_live_worker import _catalog_settings, _check_original_links
from app.sources.catalog import build_source_catalog
from scripts.ru_transport_diagnostics import transport_failure


class PollHistory:
    def __init__(self):
        self.seen = set()
        self.baselined = set()

    def observe(self, source, notices):
        keys = {original_notice_key(n) for n in notices}
        if not keys or any(n.source != source for n in notices):
            raise ValueError("Empty or mismatched successful poll")
        first = source not in self.baselined
        unseen = keys - self.seen
        result = {"baseline": first, "numbers": sorted(k[1] for k in keys),
                  "baseline_numbers": sorted(k[1] for k in unseen) if first else [],
                  "newly_observed_numbers": [] if first else sorted(k[1] for k in unseen),
                  "already_observed_numbers": sorted(k[1] for k in keys & self.seen)}
        self.seen.update(keys)
        self.baselined.add(source)
        return result


async def poll(catalog, history, sources):
    result = {"observed_at": datetime.now(timezone.utc).isoformat(), "sources": {}}
    for key in sources:
        try:
            notices = await catalog.registry.get(key).source.fetch(limit=5)
            if key == EIS:
                await _check_original_links(notices[:2])
            delta = history.observe(key, notices)
            result["sources"][key] = {"state": "PASS", **delta}
        except Exception as error:
            # Failed polls must not reset the baseline or erase past identities.
            result["sources"][key] = {"state": "BLOCKED", **transport_failure(error)}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--polls", type=int, default=2, choices=range(2, 5))
    parser.add_argument("--interval-seconds", type=int, default=60, choices=range(60, 601))
    args = parser.parse_args(argv)
    catalog = build_source_catalog(replace(_catalog_settings(), ru_ingushetia_fabrikant44_enabled=True))
    history = PollHistory()
    failed = False
    new = 0
    for index in range(args.polls):
        if index:
            time.sleep(args.interval_seconds)
        result = asyncio.run(poll(catalog, history, (EIS, FAB)))
        failed |= any(s["state"] != "PASS" for s in result["sources"].values())
        new += sum(len(s.get("newly_observed_numbers", ())) for s in result["sources"].values())
        print("INGUSHETIA_LIVE_POLL=" + json.dumps(result, sort_keys=True), flush=True)
    print("NEW_ORIGINAL_IDS_OBSERVED=" + str(new))
    print("UPSTREAM_NEW_PUBLICATION_PROVEN=NO; TELEGRAM_REQUESTS=0; PRODUCTION_CHANGED=NO")
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
