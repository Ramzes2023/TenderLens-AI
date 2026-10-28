"""Strict publisher-only transport matrix for stuck RU regional source PRs.

This is NOT source integration, tender extraction, paid research, authentication,
a proxy experiment or a TLS bypass. A web result/snippet is not a verified
official original. No account, production DB, email, Telegram or bot access.

It exists because #313, #300, #191 report opaque connector failures.
Each target is fixed in source and requested as a bounded, verified HTTPS GET
with pinned public DNS IP, hostname-verified TLS and no redirects.
The strict shared reader forbids query parameters, so these tests establish
only generic publisher-host transport; they DO NOT prove region filtering.
"""
from __future__ import annotations

import json
import ssl
from concurrent.futures import ThreadPoolExecutor

from scripts.ru_trusted_live_probe import (
    Non200OfficialResponse, Target, UnsafeAddress, describe, read_public,
)

# The regional Fabrikant catalogue is a MIRROR of EIS notices, NOT a second
# source for counting unique publications. Both hostnames appear in official
# Fabrikant pages and are probed only to understand the broken transport.
# Only literal, immutable, query-free public paths are used. The real adapters'
region-filtered list queries must still pass their own strict live tests.
TARGETS = {
    "ingushetia_eis_rss": Target(
        "zakupki.gov.ru",
        "/epz/order/extendedsearch/rss.html",
        "rss",
    ),
    "ingushetia_fabrikant_44": Target(
        "44.fabrikant.ru",
        "/44/catalog/procedure/published",
    ),
    "ingushetia_fabrikant_soap4": Target(
        "soap4.fabrikant.ru",
        "/44/catalog/procedure/published",
    ),
    "chechnya_fabrikant_44": Target(
        "44.fabrikant.ru",
        "/44/catalog/procedure/published",
    ),
    "chechnya_fabrikant_soap4": Target(
        "soap4.fabrikant.ru",
        "/44/catalog/procedure/published",
    ),
    "samara_firstparty_grid": Target(
        "webtorgi.samregion.ru", "/smallpurchases/GzwSP/NoticesGrid",
    ),
}

# Never treat an unexpected DNS/private-address error as an invitation to
# disable SSRF protections or force an unsafe endpoint.
def probe(label: str, *, reader=read_public) -> dict[str, object]:
    target = TARGETS[label]
    status: dict[str, object] = {"label": label, "classification": "BLOCKED"}
    try:
        _, payload = reader(target)
        counts = describe(target.mode, payload)
        status.update(
            classification="HTTPS_VISIBLE_NOT_ORIGINAL_VERIFIED",
            body_bytes=len(payload),
            structural_tokens=counts,
        )
    except Non200OfficialResponse as exc:
        status.update(classification="OFFICIAL_HTTP_NON200", status=exc.status)
    except (ssl.SSLError, OSError, TimeoutError, UnsafeAddress, ValueError) as exc:
        status["failure_class"] = type(exc).__name__
    return status


def main() -> int:
    if len(TARGETS) != 6:
        print("RU_REGIONAL_TRANSPORT=BLOCKED_INVALID_ALLOWLIST")
        return 2
    # Two parallel immutable connections, no browser automation, no login.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(probe, tuple(TARGETS)))
    for result in results:
        print("RU_REGIONAL_PUBLIC_ORIGIN=" + json.dumps(result, sort_keys=True))
    visible = sum(r["classification"] == "HTTPS_VISIBLE_NOT_ORIGINAL_VERIFIED"
                  for r in results)
    print(f"OFFICIAL_HTTPS_VISIBLE={visible}/{len(results)}")
    print("REGION_FILTER_APPLIED=NO")
    print("CURRENT_OPEN_TENDER_ORIGINALS_CONFIRMED=0")
    print("WORKER_SQL_SEARCH_CONFIRMED=NO")
    print("EIS_MIRRORS_COUNTED_AS_DISTINCT=NO")
    print("PRODUCTION_CHANGED=NO")
    return 0  # Reporting result only, never claim green release gate.


if __name__ == "__main__":
    raise SystemExit(main())
