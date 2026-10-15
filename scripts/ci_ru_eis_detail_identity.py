"""Host-only, strict independent EIS 44/223 individual detail identity probe.

A public RSS item's own link or title does not establish independently verified
detail content. This script fetches the actual official HTML detail page over
pinned scoped TLS, checks the exact procurement number in the returned HTML,
and reports bounded counts only. No redirects, browser, credentials, CAPTCHA
circumvention, production changes, or alternate sources.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.sources.catalog import build_source_catalog
from app.sources.http import FetchPolicy, bounded_fetch, source_client
from scripts.ru_eis_pinned_tls_probe import official_download, verify_root
from scripts.ru_public_live_smoke import _settings

SOURCES = ("eis", "eis_223")
MAX_FEED_ITEMS = 10
MAX_DETAIL_REQUESTS = 2
MAX_HTML_BYTES = 1024 * 1024
NOTICE_NUMBER_RE = re.compile(r"(?<![0-9])[0-9]{11,20}(?![0-9])")
ALLOWED_PATH_PREFIXES = ("/epz/order/notice/", "/223/purchase/public/purchase/info/")


def detail_candidate(notice, key):
    """Return an official safe detail URL + candidate number, never fetch a new host."""
    if notice.source != key:
        raise ValueError("WRONG_SOURCE")
    raw = notice.url
    if not isinstance(raw, str) or len(raw) > 2000 or any(
        ord(c) <= 32 or c.isspace() or c == "\\" for c in raw
    ):
        raise ValueError("UNSAFE_DETAIL_URL")
    parts = urlsplit(raw)
    if (parts.scheme != "https" or parts.hostname != "zakupki.gov.ru"
            or parts.netloc != "zakupki.gov.ru"
            or parts.username is not None or parts.password is not None
            or parts.port is not None or parts.fragment
            or not parts.path.startswith(ALLOWED_PATH_PREFIXES)
            or parts.path.lower().endswith(".rss")):
        raise ValueError("UNSAFE_DETAIL_URL")
    tokens = parse_qs(parts.query, keep_blank_values=True)
    candidates = []
    number = getattr(notice, "tender_number", None)
    if isinstance(number, str) and NOTICE_NUMBER_RE.fullmatch(number):
        candidates.append(number)
    for field in ("regNumber", "registrationNumber", "purchaseNumber"):
        for value in tokens.get(field, ()):
            if NOTICE_NUMBER_RE.fullmatch(value):
                candidates.append(value)
    if not candidates:
        raise ValueError("NUMBER_NOT_AVAILABLE")
    if len(set(candidates)) != 1:
        raise ValueError("AMBIGUOUS_NOTICE_NUMBER")
    return raw, candidates[0]


def detail_page_has_identity(body: bytes, number: str, content_type: str) -> bool:
    """One matching number in independently fetched HTML; no HTML alone = proof."""
    if not (isinstance(body, bytes) and 0 < len(body) <= MAX_HTML_BYTES
            and isinstance(number, str) and NOTICE_NUMBER_RE.fullmatch(number)
            and isinstance(content_type, str)
            and (content_type.split(";", 1)[0].lower().strip()
                 in ("text/html", "application/xhtml+xml"))):
        return False
    text = body.decode("utf-8-sig", errors="replace")
    if re.search(r"captcha|recaptcha|hcaptcha|провер.{0,20}робот|access denied",
                 text, re.IGNORECASE):
        return False
    return re.search(r"(?<![0-9])" + re.escape(number) + r"(?![0-9])", text) is not None


async def inspect_source(catalog, key):
    adapter = catalog.registry.get(key).source
    notices = await asyncio.wait_for(adapter.fetch(limit=MAX_FEED_ITEMS), timeout=35)
    if not notices:
        return {"rss": 0, "eligible": 0, "requested": 0, "verified": 0,
                "http_ok": 0, "blocked": "NO_PUBLIC_RSS"}
    candidates = []
    seen = set()
    for notice in notices:
        try:
            link, number = detail_candidate(notice, key)
        except ValueError:
            continue
        if (link, number) not in seen:
            candidates.append((link, number))
            seen.add((link, number))
    records = {"rss": len(notices), "eligible": len(candidates), "requested": 0,
               "verified": 0, "http_ok": 0, "blocked": None}
    if not candidates:
        records["blocked"] = "NO_SAFE_NUMBERED_DETAIL"
        return records

    # Reuse the audited public-IP/direct-only adapter transport; the trust file
    # can only be scoped to EIS in the catalog. No redirects or proxy transport.
    ssl_verify = str(adapter.ca_bundle_file)
    with bounded_fetch(FetchPolicy(frozenset({"zakupki.gov.ru"}),
                                   MAX_DETAIL_REQUESTS, max_bytes=MAX_HTML_BYTES)):
        async with source_client(
            verify=ssl_verify, timeout=15, trust_env=False,
            follow_redirects=False, headers={"Accept": "text/html"},
        ) as client:
            for link, number in candidates[:MAX_DETAIL_REQUESTS]:
                records["requested"] += 1
                try:
                    response = await asyncio.wait_for(client.get(link), timeout=20)
                    if response.status_code == 200:
                        records["http_ok"] += 1
                        if detail_page_has_identity(response.content, number,
                                                    response.headers.get("content-type", "")):
                            records["verified"] += 1
                except Exception:
                    # Do not log URL, exception text or page contents.
                    pass
    if not records["verified"]:
        records["blocked"] = "NO_INDEPENDENT_MATCH"
    return records


def strict_acceptance(data: bytes) -> bool:
    pem = verify_root(data)
    with tempfile.TemporaryDirectory(prefix="valyqon-eis-details-") as directory:
        cert = Path(directory) / "eis-root.pem"
        cert.write_text(pem, encoding="ascii", newline="\n")
        previous = os.environ.get("VALYQON_RU_EIS_CA_CERT")
        try:
            os.environ["VALYQON_RU_EIS_CA_CERT"] = str(cert)
            catalog = build_source_catalog(_settings())
            if any(key not in catalog.enabled_keys for key in SOURCES):
                raise ValueError("REQUIRED_SOURCE_DISABLED")
            verified = True
            for key in SOURCES:
                try:
                    outcome = asyncio.run(inspect_source(catalog, key))
                except Exception as error:
                    outcome = {"rss": 0, "eligible": 0, "requested": 0,
                               "verified": 0, "http_ok": 0,
                               "blocked": "FETCH_OR_TRANSPORT_" + type(error).__name__}
                print("EIS_DETAIL_SOURCE=" + key
                      + "; RSS=" + str(outcome["rss"])
                      + "; ELIGIBLE=" + str(outcome["eligible"])
                      + "; REQUESTED=" + str(outcome["requested"])
                      + "; HTTP_OK=" + str(outcome["http_ok"])
                      + "; VERIFIED=" + str(outcome["verified"])
                      + "; BLOCKER=" + str(outcome["blocked"]), flush=True)
                if outcome["verified"] < 1:
                    verified = False
            return verified
        finally:
            if previous is None:
                os.environ.pop("VALYQON_RU_EIS_CA_CERT", None)
            else:
                os.environ["VALYQON_RU_EIS_CA_CERT"] = previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-cer", type=Path, default=None)
    args = parser.parse_args()
    try:
        data = args.root_cer.read_bytes() if args.root_cer else official_download()
        result = strict_acceptance(data)
    except Exception as error:
        print("EIS_DETAIL_IDENTITY=BLOCKED", flush=True)
        print("FAILURE_CLASS=" + type(error).__name__, flush=True)
        print("SYSTEM_TRUST_CHANGED=NO; PRODUCTION_CHANGED=NO", flush=True)
        return 2
    print("EIS_DETAIL_IDENTITY=" + ("PASS" if result else "BLOCKED"), flush=True)
    print("EIS_DETAIL_MATCH_CONFIDENCE=" +
          ("OFFICIAL_HTML_EXACT_NOTICE_NUMBER" if result else "NOT_VERIFIED"),
          flush=True)
    print("DOCUMENT_DOWNLOAD_VERIFIED=NO; GENERATIVE_AI_VERIFIED=NO", flush=True)
    print("SYSTEM_TRUST_CHANGED=NO; PRODUCTION_CHANGED=NO", flush=True)
    return 0 if result else 3


if __name__ == "__main__":
    raise SystemExit(main())
