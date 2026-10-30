"""Operator-only real EIS 44/223 RSS route candidates; no deployment or SQL writes.

Use from a trusted, already EIS-reachable Windows/WSL checkout:
  python -B -m scripts.ru_eis_candidate_route_probe

The two URL path spellings are candidates, not evidence of an official API.
This tests only fixed procurement-domain URLs with scoped pinned CA trust,
strict law/identity checks and conservative future-deadline eligibility.
"""
from __future__ import annotations

import asyncio
import tempfile
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.api.public_eis_identity import accepted_eis_original
from app.api.public_source_deadline import eligible_published_deadline
from app.sources.eis_rss import (
    EisRssSource, SourceError, build_eis_rss_url, validate_eis_direct_urls,
)
from app.sources.eis_223_rss import (
    Eis223RssSource, _validate_feed_url, build_eis_223_rss_url,
)
from app.sources.http import ConnectorTransportError
from scripts.ru_eis_pinned_tls_probe import verify_root

ROOT = Path(__file__).resolve().parents[1]
CA_FILE = ROOT / "russian_trusted_root_ca_pem.crt"
PATHS = ("/epz/order/extendedsearch/rss.html", "/epz/order/extendedsearch/rss")
KEYS = ("eis", "eis_223")
MAX_ITEMS_PER_ATTEMPT = 12


def candidate_url(key: str, path: str) -> str:
    if key not in KEYS or path not in PATHS:
        raise ValueError("Unsupported EIS key or RSS path")
    default = (build_eis_rss_url("поставка") if key == "eis"
               else build_eis_223_rss_url("поставка"))
    parsed = urlsplit(default)
    url = urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))
    validate_eis_direct_urls((url,))
    if key == "eis_223":
        _validate_feed_url(url)
    return url


def active_official_count(notices: object, key: str, now: datetime) -> int:
    if key not in KEYS or not isinstance(notices, list):
        raise ValueError("Invalid EIS notices")
    result = 0
    for item in notices:
        try:
            row = asdict(item)
            if (row.get("source") == key
                    and accepted_eis_original(row)
                    and eligible_published_deadline(key, row.get("deadline"), now=now)):
                result += 1
        except (TypeError, ValueError):
            continue
    return result


def deadline_diagnostic_counts(notices: object, key: str, now: datetime) -> dict[str, int]:
    """Aggregate ONLY; no tender text, ids, raw dates or URLs escape this process."""
    from datetime import datetime as _datetime
    if key not in KEYS or not isinstance(notices, list):
        raise ValueError("Invalid source/notices")
    if now.tzinfo is None:
        raise ValueError("Aware clock required")
    counts = {
        "identity_rejected": 0,
        "deadline_missing": 0,
        "deadline_invalid": 0,
        "deadline_not_safely_future": 0,
        "open_verified": 0,
    }
    for item in notices:
        row = asdict(item)
        if row.get("source") != key or not accepted_eis_original(row):
            counts["identity_rejected"] += 1
            continue
        raw = row.get("deadline")
        if raw is None or raw == "":
            counts["deadline_missing"] += 1
            continue
        if not isinstance(raw, str) or len(raw) > 48:
            counts["deadline_invalid"] += 1
            continue
        try:
            fmt = "%d.%m.%Y %H:%M:%S" if raw.count(":") == 2 else "%d.%m.%Y %H:%M"
            local_deadline = _datetime.strptime(raw, fmt)
        except ValueError:
            counts["deadline_invalid"] += 1
            continue
        if eligible_published_deadline(key, raw, now=now):
            counts["open_verified"] += 1
        else:
            # Unknown EIS timezone; no guess about expiration or activity.
            counts["deadline_not_safely_future"] += 1
    return counts


async def probe(key: str, path: str, ca: Path, now: datetime) -> dict:
    url = candidate_url(key, path)
    factory = EisRssSource if key == "eis" else Eis223RssSource
    adapter = factory((url,), timeout=14, ca_bundle_file=ca, direct=True)
    try:
        rows = await asyncio.wait_for(adapter.fetch(limit=MAX_ITEMS_PER_ATTEMPT), timeout=23)
        counters = deadline_diagnostic_counts(rows, key, now)
        active = counters["open_verified"]
        return {"status": "ACTIVE_CANDIDATE" if active else "NO_CURRENT_VERIFIED_ORIGINALS",
                "retrieved": len(rows), "active": active, "diagnostic": counters}
    except ConnectorTransportError as exc:
        reason = exc.reason if exc.reason in {
            "http_status", "http_transient", "network", "tls_certificate",
            "public_ip", "policy", "response_size",
        } else "other"
        return {"status": "TRANSPORT_BLOCKED", "reason": reason}
    except asyncio.TimeoutError:
        return {"status": "TRANSPORT_BLOCKED", "reason": "overall_timeout"}
    except SourceError:
        return {"status": "RSS_LAW_OR_XML_NOT_VERIFIED"}
    except Exception as exc:
        # No exception details, URLs, response bodies, purchase records or local paths.
        return {"status": "OTHER_BLOCKED", "class": type(exc).__name__[:50]}


async def inspect(ca: Path) -> dict:
    now = datetime.now(timezone.utc)
    result = {}
    for key in KEYS:
        for path in PATHS:
            result[(key, path)] = await probe(key, path, ca, now)
    return result


def main() -> int:
    print("EIS_ROUTE_CANDIDATE_TEST=START", flush=True)
    print("NETWORK_VANTAGE=LOCAL_OPERATOR_NOT_PUBLIC_VPS", flush=True)
    try:
        pem = verify_root(CA_FILE.read_bytes())
        with tempfile.TemporaryDirectory(prefix="valyqon-eis-route-") as d:
            ca = Path(d) / "eis-only.pem"
            ca.write_text(pem, encoding="ascii", newline="\n")
            outcomes = asyncio.run(inspect(ca))
    except (ValueError, OSError) as exc:
        print("EIS_ROUTE_CANDIDATE_TEST=BLOCKED_CA_OR_ENV", flush=True)
        print("ERROR_CLASS=" + type(exc).__name__[:50], flush=True)
        print("PUBLIC_SITE_CHANGED=NO", flush=True)
        return 2

    success = set()
    for (key, path), data in outcomes.items():
        law = "44" if key == "eis" else "223"
        name = "HTML_SUFFIX" if path.endswith(".html") else "NO_SUFFIX"
        prefix = "EIS_" + law + "_" + name
        print(prefix + "_STATUS=" + data["status"], flush=True)
        if "retrieved" in data:
            print(prefix + "_RSS_ITEMS=" + str(data["retrieved"]), flush=True)
            print(prefix + "_OPEN_VERIFIED_ORIGINALS=" + str(data["active"]), flush=True)
            if data["active"]:
                success.add(key)
        if "diagnostic" in data:
            for name, value in data["diagnostic"].items():
                print(prefix + "_CATEGORY_" + name.upper() + "=" + str(value), flush=True)
        if "reason" in data:
            print(prefix + "_REASON=" + data["reason"], flush=True)
        if "class" in data:
            print(prefix + "_ERROR_CLASS=" + data["class"], flush=True)

    both = all(k in success for k in KEYS)
    print("EIS_44_223_LOCAL_LIVE_CANDIDATES=" + ("PASS" if both else "BLOCKED"),
          flush=True)
    print("EIS_VPS_WORKER_SQL_PUBLIC_HTTPS=NOT_VERIFIED", flush=True)
    print("EIS_PUBLIC_DEPLOYMENT=NOT_PERFORMED", flush=True)
    print("TLS_BYPASS=NO; PRODUCTION_MODIFIED=NO", flush=True)
    return 0 if both else 2


if __name__ == "__main__":
    raise SystemExit(main())
