"""First-party read-only network evidence for stalled VALYQON Russian sources.

This is a bounded diagnostic, not procurement collection: official origin
HTTPS only, certificate and SNI verified, DNS addresses must all be globally
routable, no redirects, no credentials/proxies/cookies or user-provided URLs.
Execute only from reviewed main on named RU runner. Never count a 200 as
proof of genuine tender records, worker ingestion or customer notification.
"""
from __future__ import annotations

import json
import ssl
import xml.etree.ElementTree as ET

from scripts.ru_trusted_live_probe import TARGETS, ON_DEMAND_TARGETS, Target, UnsafeAddress, read_public, describe

# Only immutable first-party publisher addresses. EIS availability must not
# be counted as separate Chechnya and Ingushetia feeds; it is one publisher.
ROUTES = {
    "eis_44_public_listing": Target(
        "zakupki.gov.ru", "/epz/order/extendedsearch/results.html"),
    "ingushetia_accredited_fabrikant": TARGETS["fabrikant_44"],
    "fabrikant_published_listing": TARGETS["fabrikant_44_mirror"],
    "roseltorg_public": TARGETS["roseltorg"],
    "gpb_official_rss": TARGETS["gpb_rss"],
    "gpb_alternative_rss": ON_DEMAND_TARGETS["gpb_new_rss"],
    "tektorg_public": TARGETS["tektorg"],
}

def audit_one(name: str) -> dict[str, str]:
    if name not in ROUTES:
        raise ValueError("Only reviewed first-party names are allowed")
    target = ROUTES[name]
    try:
        mime, payload = read_public(target)
        counts = describe(target.mode, payload)
        # Even a correctly formed RSS channel can be empty or contain no
        # authentic procurement. No URL, content or identifier is logged.
        return {
            "state": "HTTPS_DOCUMENT_VISIBLE_NOT_TENDERS",
            "media": "rss" if target.mode == "rss" else "html",
            "document_shape": "rss_or_atom" if target.mode == "rss" else "html",
            "rss_item_count": str(counts.get("rss_items", 0)
                                  + counts.get("atom_items", 0)),
        }
    except (OSError, ssl.SSLError, UnsafeAddress, ValueError, ET.ParseError) as error:
        return {"state": "BLOCKED", "safe_failure_class": type(error).__name__}


def main() -> int:
    results = {name: audit_one(name) for name in ROUTES}
    for name, result in results.items():
        print("RU_TRUSTED_SOURCE_CHECK=" + json.dumps({
            "source": name, **result
        }, sort_keys=True), flush=True)
    count = sum(x["state"] == "HTTPS_DOCUMENT_VISIBLE_NOT_TENDERS"
                for x in results.values())
    print(f"RU_TRUSTED_HTTPS_VISIBLE_ONLY={count}/{len(ROUTES)}")
    print("RU_TRUSTED_ORIGINAL_DETAIL_VERIFIED=NO")
    print("RU_TRUSTED_WORKER_SQL_INGESTED=NO")
    print("RU_TRUSTED_CUSTOMER_DELIVERY=NO")
    print("PRODUCTION_CHANGED=NO")
    # The diagnostics job is successful if it safely observed the network.
    # Release gates remain source-owned, current genuine original->Worker SQL.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
