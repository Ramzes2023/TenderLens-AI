"""Automatic *read-only* Russian trust-zone transport survey after reviewed main merge.

Not a connector, ingestion workflow, Telegram test, anti-bot bypass or verified
original notice. Run only from reviewed main on the explicitly named RU runner.
No credentials, proxy, redirect, TLS bypass, arbitrary destinations or content
in diagnostics. The dependency pins public resolved IPs while TLS still verifies
the official exact hostname.
"""
from __future__ import annotations

import json
import ssl
import xml.etree.ElementTree as ET

from scripts.ru_trusted_live_probe import (
    TARGETS, Target, UnsafeAddress, describe, read_public,
)

# Exactly one official endpoint per publisher route, plus the real EIS root
# for a safe network/TLS check. EIS root does NOT prove a filtered regional RSS.
# Fabrikant / EIS 44-FZ are not independent source counts for Ingushetia.
TARGETS_READONLY = {
    "eis_regional_network_only": Target("zakupki.gov.ru", "/"),
    "ingushetia_fabrikant_public": TARGETS["fabrikant_44"],
    "chechnya_eis_network_only": Target("zakupki.gov.ru", "/"),
    "roseltorg_public": TARGETS["roseltorg"],
    "gpb_official_rss": TARGETS["gpb_rss"],
    "tektorg_public": TARGETS["tektorg"],
}
# EIS regional searches use the same host; probe it exactly once.
PROBE_ORDER = (
    "eis_regional_network_only",
    "ingushetia_fabrikant_public",
    "roseltorg_public",
    "gpb_official_rss",
    "tektorg_public",
)
MAX_UNIQUE_READS = 5


def observe_one(label: str, *, reader=read_public) -> dict[str, object]:
    """Report only a stable network state, not addresses, payload, or tenders."""
    if type(label) is not str or label not in TARGETS_READONLY:
        raise ValueError("Source identifier is not on the fixed public allowlist")
    target = TARGETS_READONLY[label]
    try:
        media, payload = reader(target)
        counts = describe(target.mode, payload)
        return {
            "status": "RSS_VISIBLE_NOT_INGESTED" if target.mode == "rss"
                      else "HTML_VISIBLE_NOT_INGESTED",
            "bytes": len(payload),
            "safe_counts": counts,
        }
    except (OSError, ValueError, UnsafeAddress, ET.ParseError, ssl.SSLError) as error:
        return {"status": "BLOCKED", "failure_class": type(error).__name__}


def observe_all(*, runner=None, reader=read_public):
    """Hard refuse any wrong runner before DNS, TLS, requests or checkout code.

    GitHub workflow also checks runner.name before source checkout. This
    independent in-process guard limits accidental operator CLI misuse.
    """
    if runner != "VALYQON-RU-01":
        raise PermissionError("Trusted RU runner required")
    if len(PROBE_ORDER) > MAX_UNIQUE_READS:
        raise ValueError("Fixed publisher read budget exceeded")
    pairs = [(TARGETS_READONLY[key].host, TARGETS_READONLY[key].path)
             for key in PROBE_ORDER]
    if len(set(pairs)) != len(pairs):
        raise ValueError("Duplicate publisher requests")
    observations = {}
    for key in PROBE_ORDER:
        observations[key] = observe_one(key, reader=reader)
    # One official EIS DNS/TLS observation cannot be interpreted as a regional
    # successful Chechnya or Ingushetia tenders source.
    observations["chechnya_eis_network_only"] = {
        **observations["eis_regional_network_only"],
        "reused_official_eis_transport": True,
    }
    return observations


def main() -> int:
    import os
    import sys
    if os.getenv("RUNNER_NAME") != "VALYQON-RU-01":
        print("RU_TRUSTED_SURVEY=BLOCKED_WRONG_RUNNER")
        return 2
    try:
        results = observe_all(runner=os.getenv("RUNNER_NAME"))
    except (PermissionError, ValueError):
        print("RU_TRUSTED_SURVEY=BLOCKED_POLICY")
        return 2
    for label, result in sorted(results.items()):
        print("RU_TRUSTED_SOURCE=" + json.dumps(
            {"source": label, **result}, sort_keys=True,
        ))
    print("RU_TRUSTED_ORIGINAL_DETAIL_VERIFIED=NO")
    print("RU_TRUSTED_WORKER_SQL_VERIFIED=NO")
    print("RU_TRUSTED_CUSTOMER_ALERT_ACK=NO")
    print("PRODUCTION_CHANGED=NO")
    # Read-only observations are not a real-data acceptance gate. Any BLOCKED
    # here must remain blocked in the actual source-owned acceptance workflows.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
