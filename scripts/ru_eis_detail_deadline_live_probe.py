"""Read-only, operator-local real official EIS RSS -> detail deadline diagnostic.

This is NOT an always-on Worker or deployment. It writes no procurement
records, secrets, notifications or production volumes. It requires the
repository's fingerprint-pinned Russian root CA, HTTPS-only official paths,
direct transport and no redirects. 223-FZ HTTP access failures block that law.
"""
from __future__ import annotations

import asyncio
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.api.public_eis_identity import accepted_eis_original
from app.sources.eis_rss import EisRssSource, build_eis_rss_url, SourceError
from app.sources.eis_223_rss import Eis223RssSource, build_eis_223_rss_url
from app.sources.eis_official_detail_deadline import (
    MAX_HTML_BYTES, verified_detail_deadline,
)
from app.sources.http import (
    ConnectorTransportError, FetchPolicy, bounded_fetch, source_client,
)
from scripts.ru_eis_pinned_tls_probe import verify_root

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILE = ROOT / "russian_trusted_root_ca_pem.crt"
PER_LAW_DETAIL_LIMIT = 3


async def probe_law(key: str, ca: Path, now: datetime) -> dict:
    if key not in ("eis", "eis_223"):
        raise ValueError("Unapproved EIS law")
    is_44 = key == "eis"
    feed = (EisRssSource((build_eis_rss_url("поставка"),), timeout=12,
                         ca_bundle_file=ca, direct=True) if is_44 else
            Eis223RssSource((build_eis_223_rss_url("поставка"),), timeout=12,
                            ca_bundle_file=ca, direct=True))
    result = {
        "rss_items": 0, "attempts": 0, "http_200": 0,
        "current_originals": 0, "no_current_verified_deadline": 0,
        "publisher_rejected": 0, "transport_blocked": 0,
        "invalid_official_identity": 0, "invalid_html": 0,
    }
    try:
        rows = await asyncio.wait_for(feed.fetch(limit=12), timeout=21)
    except Exception as error:
        result["rss_stage_error"] = (
            error.reason if isinstance(error, ConnectorTransportError)
            and error.reason in {"network", "http_status", "tls_certificate",
                                 "public_ip", "http_transient", "response_size", "policy"}
            else type(error).__name__[:48]
        )
        return result
    result["rss_items"] = len(rows)
    candidates = []
    for notice in rows:
        if accepted_eis_original(asdict(notice)) and notice.source == key:
            candidates.append(notice)
        else:
            result["invalid_official_identity"] += 1
    with bounded_fetch(
        FetchPolicy(frozenset({"zakupki.gov.ru"}),
                    PER_LAW_DETAIL_LIMIT, max_bytes=MAX_HTML_BYTES)
    ):
        async with source_client(
            timeout=12,
            trust_env=False,
            follow_redirects=False,
            verify=str(ca),
            headers={"Accept": "text/html"},
        ) as client:
            for notice in candidates[:PER_LAW_DETAIL_LIMIT]:
                result["attempts"] += 1
                try:
                    response = await asyncio.wait_for(client.get(notice.url), timeout=16)
                    response.raise_for_status()
                    result["http_200"] += 1
                    if ("html" not in response.headers.get("content-type", "").lower()
                            or len(response.content) > MAX_HTML_BYTES):
                        result["invalid_html"] += 1
                        continue
                    closing = verified_detail_deadline(notice, response.content, now=now)
                    if closing:
                        result["current_originals"] += 1
                    else:
                        result["no_current_verified_deadline"] += 1
                except ConnectorTransportError as error:
                    if error.reason == "http_status":
                        result["publisher_rejected"] += 1
                        # Do not hammer an origin that is rejecting individual detail reads.
                        break
                    result["transport_blocked"] += 1
                    break
                except (TimeoutError, OSError, SourceError):
                    result["transport_blocked"] += 1
                    break
    return result


async def inspect(ca: Path):
    now = datetime.now(timezone.utc)
    results = {}
    for key in ("eis", "eis_223"):
        try:
            results[key] = await probe_law(key, ca, now)
        except Exception as error:
            results[key] = {"probe_error_class": type(error).__name__[:48]}
    return results


def main() -> int:
    print("EIS_OFFICIAL_DETAIL_LIVE_PROBE=START", flush=True)
    try:
        pem = verify_root(ROOT_FILE.read_bytes())
        with tempfile.TemporaryDirectory(prefix="valyqon-eis-detail-") as directory:
            ca = Path(directory) / "trusted-eis-only.pem"
            ca.write_text(pem, encoding="ascii", newline="\n")
            results = asyncio.run(inspect(ca))
    except Exception as error:
        print("EIS_OFFICIAL_DETAIL_LIVE_PROBE=BLOCKED_CERT_OR_RUNTIME", flush=True)
        print("ERROR_CLASS=" + type(error).__name__[:48], flush=True)
        print("PRODUCTION_CHANGED=NO", flush=True)
        return 2

    for key, counters in results.items():
        prefix = "EIS_44" if key == "eis" else "EIS_223"
        for field, number in counters.items():
            print(prefix + "_" + field.upper() + "=" + str(number), flush=True)

    ready = all(results.get(key, {}).get("current_originals", 0) > 0
                for key in ("eis", "eis_223"))
    print("BOTH_LAWS_CURRENT_ORIGINAL_DETAILS=" + ("PASS" if ready else "BLOCKED"),
          flush=True)
    print("VPS_EGRESS=NOT_TESTED; V6_SQL_AND_PUBLIC_HTTPS=NOT_TESTED", flush=True)
    print("PRODUCTION_CHANGED=NO; TLS_BYPASS=NO; NOTICES_LOGGED=NO", flush=True)
    print("EIS_PUBLIC_DEPLOYMENT=NOT_PERFORMED", flush=True)
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
