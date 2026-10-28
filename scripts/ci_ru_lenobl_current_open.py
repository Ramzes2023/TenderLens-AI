"""Official Lenobl independently verified open-offer original-clock gate.

This is a genuine first-party GET list + up to six independently
verified details. The parser preserves the published local DATE+TIME without timezone;
its clock has no independently documented timezone. Expired/ambiguous local times are excluded using the maximum
worldwide local clock UTC+14, with no invented time zone.

No persistent DB, Caddy, user data, credentials, alerts, or test fixtures.
A PASS is not proof that a VPS Worker or public HTTPS search is deployed.
"""
import asyncio
import json
from datetime import datetime, timezone

from app.api.public_source_deadline import eligible_published_deadline
from app.sources.lenobl_small_public import LenoblSmallPublicSource, SOURCE_ID


def acceptance():
    notices=asyncio.run(LenoblSmallPublicSource(timeout=25).fetch(6))
    if not 1 <= len(notices) <= 6 or len({n.external_id for n in notices}) != len(notices):
        raise AssertionError("Unverified or duplicated official Lenobl original")
    now=datetime.now(timezone.utc)
    current=[]
    for notice in notices:
        if notice.source!=SOURCE_ID or not notice.url.startswith(
                "https://zakupki.lenreg.ru/ProductRequestGroup/Index/"):
            raise AssertionError("Wrong original provenance")
        if eligible_published_deadline(SOURCE_ID,notice.deadline,now=now):
            current.append(notice.external_id)
    print("RU_LENOBL_REAL_ORIGINAL_DETAILS="+str(len(notices)))
    print("RU_LENOBL_OFFICIAL_LOCAL_CLOSING_CLOCKS="+json.dumps([n.deadline for n in notices]))
    print("RU_LENOBL_PUBLISHED_CALENDAR_DATES="+str(
        sum(n.deadline is not None for n in notices)))
    print("RU_LENOBL_SAFELY_FUTURE_ORIGINALS="+str(len(current)))
    if not current:
        raise AssertionError("No official future-day offer submission deadline")
    return len(current)


def main():
    try:
        acceptance()
    except Exception as exc:
        print("RU_LENOBL_CURRENT_OPEN=BLOCKED")
        print("FAILURE_CLASS="+type(exc).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_LENOBL_CURRENT_OPEN=PASS")
    print("REQUIRES_LEASED_WORKER_AND_PUBLIC_HTTPS=YES")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
