"""Independent current-open native original gate for Kavkaz.RF.

Read-only actual first-party list+two distinct detail GETs. Never fabricate
a clock time, reuse fixtures, treat EIS mirrors as additional unique tenders,
or claim any public VPS deployment.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.api.public_source_deadline import eligible_published_deadline
from app.sources.kavkaz_rf_firstparty import (
    KavkazRfFirstpartySource, SOURCE_ID, _canonical, NATIVE_NUMBER,
)


async def inspect_current():
    notices=await KavkazRfFirstpartySource(timeout=25).fetch(limit=2)
    if len(notices)!=2 or len({n.external_id for n in notices})!=2:
        raise AssertionError("Two distinct current first-party originals required")
    now=datetime.now(timezone.utc)
    eligible=[]
    for notice in notices:
        if (notice.source!=SOURCE_ID
                or NATIVE_NUMBER.fullmatch(notice.external_id) is None
                or notice.tender_number != notice.external_id
                or _canonical(notice.url)!=notice.url
                or not notice.published_at
                or notice.initial_price is None
                or notice.customer != "АО «КАВКАЗ.РФ»"):
            raise AssertionError("Live original identity/price/title/issuer not verified")
        if eligible_published_deadline(SOURCE_ID, notice.deadline, now=now):
            eligible.append(notice)
    if not eligible:
        raise AssertionError("No currently open original with safely future published date")
    return len(eligible)


def main():
    try:
        count=asyncio.run(inspect_current())
    except Exception as exc:
        print("KAVKAZ_PUBLIC_CURRENT_OPEN=BLOCKED")
        print("FAILURE_CLASS="+type(exc).__name__)
        print("SOURCE_ADDED_TO_PRODUCTION=NO")
        return 2
    print("KAVKAZ_PUBLIC_CURRENT_OPEN=PASS")
    print("FIRSTPARTY_CURRENT_SAFE_FUTURE_COUNT="+str(count))
    print("EIS_DEDUP_INDEPENDENCE_NOT_PROVED=YES")
    print("SOURCE_ADDED_TO_PRODUCTION=NO")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
