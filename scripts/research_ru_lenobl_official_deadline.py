"""Read-only genuine Lenobl offer-deadline research, never source activation.

The existing first-party Lenobl adapter verifies list->detail title/ID but
does not populate a deadline; this means public active-only search hides it.
Test only a *bounded* official detail and expose strictly dates/label matches.
No credentials, paid data, browser session, cookies, relaxed TLS or production
data are used. A date on a page is NOT automatically a submission deadline.
"""
from __future__ import annotations

import asyncio
import json
import re

from app.sources.http import FetchPolicy, bounded_fetch, source_client
from app.sources.lenobl_small_public import (
    HOST, LIST_URL, MAX_BYTES, MAX_DETAILS, _Detail, _html,
    parse_lenobl_listing, parse_lenobl_detail,
)

LABELS = (
    "срок окончания подачи оферт",
    "срок окончания подачи предложений",
    "окончание подачи оферт",
    "срок подачи оферт",
    "окончание подачи предложений",
    "дата окончания подачи",
    "прием оферт до",
    "приём оферт до",
    "приём предложений до",
)
DATE = re.compile(
    r"(?<![0-9])(?:[0-3][0-9]\.[01][0-9]\.20[0-9]{2}"
    r"(?:\s+(?:[01][0-9]|2[0-3]):[0-5][0-9])?"
    r"|20[0-9]{2}-[01][0-9]-[0-3][0-9]"
    r"(?:[T ][0-2][0-9]:[0-5][0-9](?::[0-5][0-9])?"
    r"(?:Z|[+-][0-2][0-9]:[0-5][0-9])?)?)(?![0-9])"
)


def classify_visible_deadline(html: bytes) -> dict:
    doc = _Detail()
    doc.feed(_html(html))
    doc.close()
    # _Detail discards script/style/template/noscript and <head>.
    visible = " ".join(" ".join(doc.visible).split())
    folded = visible.casefold().replace("ё", "е")
    candidates = []
    for label in LABELS:
        position = folded.find(label.replace("ё", "е"))
        if position < 0:
            continue
        # The bounded window is ONLY diagnostic; unrelated dates on the
        # same page can appear. Do not turn a regex into a real deadline.
        window = visible[position+len(label): position+len(label)+110]
        parsed = DATE.findall(window)
        # Mask literal text/IDs entirely; only the *format* of the next
        # visible characters is logged so a developer can distinguish
        # alphabetic month names, placeholders and split date fields.
        shape = "".join("D" if ch.isdigit() else "A" if ch.isalpha()
                        else ch for ch in window[:85])
        candidates.append({"field":label,"nearby_dates":parsed[:2],
                           "nearby_format_shape":shape})
    return {
        "visible_label_count":len(candidates),
        "date_field_candidates":candidates[:8],
        "page_contains_any_dates":bool(DATE.search(visible)),
        "title_count":len(doc.headings),
        "is_verified_submission_deadline":False,
    }


async def diagnose() -> list[dict]:
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 1+MAX_DETAILS,
                                   max_bytes=MAX_BYTES)):
        async with source_client(timeout=25, follow_redirects=False,
                                 trust_env=False,
                                 headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"}) as client:
            response=await client.get(LIST_URL)
            response.raise_for_status()
            if "html" not in response.headers.get("content-type","").lower():
                raise ValueError("Publisher public list not HTML")
            rows=parse_lenobl_listing(response.content,limit=MAX_DETAILS)
            diagnostics=[]
            skipped=0
            for identity,url,title in rows:
                try:
                    reply=await client.get(url)
                    reply.raise_for_status()
                    if "html" not in reply.headers.get("content-type","").lower():
                        raise ValueError("Publisher individual detail not HTML")
                    verified=parse_lenobl_detail(reply.content,identity=identity,
                                                 url=url,listing_title=title)
                    record=classify_visible_deadline(reply.content)
                except ValueError:
                    # Some published list cards may be inconsistent or
                    # withdraw their details. Mirror the actual connector:
                    # skip unverified originals, never synthesize an identity.
                    skipped+=1
                    continue
                diagnostics.append({
                    "native_original_verified":verified.external_id==identity,
                    "official_host":HOST,
                    "deadline_details":record,
                    "source_active_ready":False,
                })
            if not diagnostics:
                raise ValueError("No independently verified original details")
            print("RU_LENOBL_UNVERIFIED_DETAIL_COUNT="+str(skipped))
            return diagnostics


def main() -> int:
    try:
        diagnostics=asyncio.run(diagnose())
    except Exception as exc:
        print("RU_LENOBL_DEADLINE_DIAGNOSTIC=BLOCKED")
        print("FAILURE_CLASS="+type(exc).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2
    for i,record in enumerate(diagnostics):
        print("RU_LENOBL_OFFICIAL_DETAIL_"+str(i+1)+"="+json.dumps(
            record,ensure_ascii=False,sort_keys=True))
    print("RU_LENOBL_REAL_ORIGINAL_COUNT="+str(len(diagnostics)))
    print("RU_LENOBL_DEADLINE_DIAGNOSTIC=RESEARCH_ONLY")
    print("RU_LENOBL_PUBLIC_SITE_SOURCE_ENABLED=NO")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
