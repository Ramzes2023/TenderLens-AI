"""Strict live read-only first-party Chechnya committee catalogue→actual details.

This is discovery ONLY; it does NOT register/enable the publisher in
production, claim EIS-independent notices or send Telegram messages.
"""
from __future__ import annotations
import asyncio
import json
import re
from urllib.parse import urlsplit

from app.sources.ru_chechnya_fabrikant44 import (
    ChechnyaFabrikant44Source, HOST, INN, ORGANIZER, REGION, SOURCE_ID,
)


async def real() -> dict:
    notices = await ChechnyaFabrikant44Source(timeout=25).fetch(limit=3)
    if len(notices) < 2:
        raise AssertionError("Fewer than two independently verified original Chechnya notices")
    ids = [n.tender_number for n in notices]
    if len(set(ids)) != len(ids):
        raise AssertionError("Source original IDs duplicated")
    for n in notices:
        p = urlsplit(n.url)
        if (n.source != SOURCE_ID or n.customer != ORGANIZER
                or n.region != REGION or not re.fullmatch(r"[0-9]{19}", n.tender_number)
                or n.external_id != n.tender_number or
                p.scheme != "https" or p.netloc != HOST or
                not p.path.endswith("/" + n.tender_number)
                or not 5 <= len(n.title) <= 1000):
            raise AssertionError("Unverified Chechnya first-party ID/region/title")
    return {
        "firstparty_originals": len(ids),
        "numbers": ids,
        "source": SOURCE_ID,
        "org_inn_verified_on_each_detail": INN,
        "production_changed": False,
        "worker_sqlite_not_yet_verified": True,
        "real_telegram_receipt": False,
    }


def main() -> int:
    try:
        result = asyncio.run(real())
    except Exception as exc:
        print("RU_CHECHNYA_FABRIKANT_REAL=BLOCKED")
        print("FAILURE_CLASS=" + type(exc).__name__[:70])
        # Only fixed transport classifications. Never reveal upstream raw
        # errors, request URLs, cookies, tokens, supplier names or IPs.
        if type(exc).__name__ == "ConnectorTransportError":
            reason = getattr(exc, "reason", "")
            known = {"network", "public_ip", "tls_certificate", "http_status",
                     "http_transient", "response_size", "policy"}
            print("TRANSPORT_REASON=" + (reason if reason in known else "unclassified"))
            print("TRANSPORT_RETRYABLE=" + str(getattr(exc, "retryable", False) is True))
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_CHECHNYA_FABRIKANT_FIRSTPARTY=" + json.dumps(result, sort_keys=True))
    print("RU_CHECHNYA_FABRIKANT_REAL=PASS_ORIGINAL_DETAIL_ONLY")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
