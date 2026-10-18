"""Research-only official UzEx bounded second/third page district-buyer evidence.

Explicit official JSON POST endpoints, no credentials, customer profiles,
production writes, TLS override, redirects or private document calls.
"""
from __future__ import annotations
import asyncio
import json
import traceback
from datetime import datetime
from app.sources.uz_uzex import API_URL, HOST, MAX_BODY, PER_TYPE, parse_uzex_tradelist
from app.sources.http import FetchPolicy, bounded_fetch, source_client

LOCAL = ("tuman", "tumani", "viloyat", "shahar", "shaxar",
         "maktab", "mahalla", "bog'cha", "rayon", "район",
         "мактаб", "шаҳар", "ҳоким", "hokim")
# Three bounded pages per officially documented type, beyond the canonical first.
PAGES = ((21, 40), (41, 60), (61, 80))


async def execute():
    report = {"source": "uz_uzex", "production_enabled": False,
              "official_host": HOST, "pages_requested": 0,
              "valid_rows": 0, "regional_buyer_rows": 0, "open_regional_buyer_rows": 0,
              "page_stats": []}
    with bounded_fetch(FetchPolicy(frozenset({HOST}), len(PAGES) * 2, max_bytes=MAX_BODY)):
        async with source_client(timeout=16.0, trust_env=False, follow_redirects=False) as client:
            for type_id in (1, 2):
                seen_page_ids = set()
                for start, stop in PAGES:
                    response = await client.post(
                        API_URL,
                        json={"TypeId": type_id, "From": start,
                              "To": stop, "System_Id": 0},
                        headers={"Accept": "application/json",
                                 "User-Agent": "VALYQON-public-procurement-research/1.0"},
                    )
                    report["pages_requested"] += 1
                    response.raise_for_status()
                    if ("json" not in response.headers.get("content-type", "").lower()
                            or len(response.content) > MAX_BODY):
                        raise ValueError("official page rejected content contract")
                    raw = response.json()
                    if not isinstance(raw, list) or len(raw) > PER_TYPE:
                        raise ValueError("official page changed bounded row shape")
                    notices = parse_uzex_tradelist(raw, type_id=type_id) if raw else []
                    ids = {item.external_id for item in notices}
                    if ids & seen_page_ids:
                        raise ValueError("official pagination repeated previously observed page identities")
                    seen_page_ids.update(ids)
                    regional = [n for n in notices
                                if n.customer and any(x in n.customer.casefold() for x in LOCAL)]
                    open_regional = []
                    for n in regional:
                        try:
                            end = datetime.fromisoformat(n.deadline.replace("Z", "+00:00"))
                            # A naive official deadline has unspecified timezone.
                            # Never guess it is UTC or claim the bid is still open.
                            if end.tzinfo is not None and end >= datetime.now(end.tzinfo):
                                open_regional.append(n)
                        except ValueError:
                            pass
                    report["valid_rows"] += len(notices)
                    report["regional_buyer_rows"] += len(regional)
                    report["open_regional_buyer_rows"] += len(open_regional)
                    report["page_stats"].append({"type": type_id, "from": start,
                                                 "to": stop, "validated": len(notices),
                                                 "regional": len(regional),
                                                 "open_regional": len(open_regional)})
    return report


def main():
    try:
        result = asyncio.run(execute())
        result["passed"] = result["regional_buyer_rows"] > 0
    except Exception as exc:
        tb = traceback.extract_tb(exc.__traceback__)
        last = tb[-1] if tb else None
        result = {"source": "uz_uzex", "passed": False,
                  "failure_type": type(exc).__name__,
                  "safe_failure_line": last.lineno if last and
                  last.filename.endswith("ci_cis_uzex_regional_page_probe.py") else None,
                  "safe_failure_function": last.name if last and
                  last.filename.endswith("ci_cis_uzex_regional_page_probe.py") else "adapter_or_transport",
                  "production_enabled": False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
