"""Read-only genuine Fabrikant original time/price parser acceptance.

A pinned list of three previously independently authenticated first-party
URLs is used ONLY as a parser probe; it is NOT automatic procurement discovery.
No production DB, worker job, user notification or source activation occurs.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.sources.fabrikant_public_detail_terms import original_terms
from app.sources.http import FetchPolicy, bounded_fetch, source_client

HOST = "soap4.fabrikant.ru"
ORIGINALS = (
    ("ingushetia", "0114500000826002518", "0608058533",
     "Поставка организационной техники", "2026-11-06"),
    ("chechnya", "0194200000526005756", "2016014690",
     "Услуги по организации и проведению праздничных мероприятий", "2026-11-05"),
    ("chechnya", "0194200000526005775", "2016014690",
     "Поставка фармацевтических препаратов", "2026-11-05"),
)


async def prove():
    observations = []
    with bounded_fetch(FetchPolicy(frozenset({HOST}),len(ORIGINALS),
                                   max_bytes=1_800_000)):
        async with source_client(timeout=25,trust_env=False,
                                 follow_redirects=False,
                                 headers={"Accept":"text/html",
                                          "User-Agent":"Mozilla/5.0"}) as client:
            for region,number,inn,title,day in ORIGINALS:
                url=f"https://{HOST}/44/procedure/ea21/{number}"
                response=await client.get(url)
                response.raise_for_status()
                if "html" not in response.headers.get("content-type","").lower():
                    raise AssertionError("Publisher original not HTML")
                from app.sources.fabrikant_public_detail_terms import _published_visible
                visible=_published_visible(response.content).casefold()
                if not all(field.casefold() in visible for field in (number,inn,title)):
                    raise AssertionError("Official ID/title/organizer mismatch")
                terms=original_terms(response.content)
                timestamp=terms["deadline"]
                if not isinstance(timestamp,str) or not timestamp.startswith(day+"T"):
                    raise AssertionError("Unverified original closing day or timezone")
                due=datetime.fromisoformat(timestamp)
                if due.utcoffset().total_seconds()!=3*3600:
                    raise AssertionError("Moscow original timezone not preserved")
                if due.astimezone(timezone.utc) <= datetime.now(timezone.utc):
                    raise AssertionError("Official submission deadline not future")
                observations.append({"region":region,"source_original_verified":True,
                                     "future_deadline_verified":True,
                                     "price_disclosed_and_verified":terms["initial_price"] is not None})
    return observations


def main():
    try:
        result=asyncio.run(prove())
    except Exception as exc:
        print("RU_FABRIKANT_TERMS_REAL_ORIGINALS=BLOCKED")
        print("FAILURE_CLASS="+type(exc).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2
    if len(result)!=3 or len({r["region"] for r in result})!=2:
        print("RU_FABRIKANT_TERMS_REAL_ORIGINALS=BLOCKED_COUNT")
        return 2
    for index,item in enumerate(result,1):
        print("RU_FABRIKANT_ORIGINAL_"+str(index)+"="+str(item))
    print("RU_FABRIKANT_TERMS_REAL_ORIGINALS=PASS")
    print("CURRENT_FIRSTPARTY_CATALOGUE_DISCOVERY=NOT_PROVED")
    print("LEASED_WORKER_SQL_AND_HTTPS=NOT_PROVED")
    print("REGIONAL_SOURCES_ENABLED=NO")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
