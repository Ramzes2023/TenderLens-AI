"""Bounded, first-party EIS 44/223 transport classifier, NOT a source acceptance.

No user input URLs, no redirects/proxies/authentication, no response-body reads,
no secret values, no writes, no TLS bypass. A 200 is ONLY a transport candidate.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import httpx

from app.sources.eis_44_public_html import LIST_URL
from app.sources.eis_rss import build_eis_rss_url
from app.sources.eis_223_rss import build_eis_223_rss_url
from scripts.ru_eis_pinned_tls_probe import verify_root

TARGETS = {
    "EIS_44_HTML": LIST_URL,
    "EIS_44_RSS": build_eis_rss_url("поставка"),
    "EIS_223_RSS": build_eis_223_rss_url("поставка"),
}


def classify(status: int, content_type: str, target: str) -> str:
    """A transport candidate never implies a valid live original."""
    if status in {403, 429}:
        return "PUBLISHER_DENIED_OR_RATE_LIMITED"
    if status in {404, 410}:
        return "OFFICIAL_ROUTE_NOT_FOUND"
    if 300 <= status < 400:
        return "REDIRECT_BLOCKED"
    if status != 200:
        return "UPSTREAM_HTTP_" + str(status)
    kind = content_type.lower().split(";", 1)[0].strip()
    if target.endswith("HTML") and kind in {"text/html", "application/xhtml+xml"}:
        return "HTTP_200_HTML_UNPARSED"
    if target.endswith("RSS") and kind in {
        "application/rss+xml", "application/atom+xml", "application/xml", "text/xml"
    }:
        return "HTTP_200_XML_UNPARSED"
    return "HTTP_200_UNEXPECTED_MEDIA_TYPE"


def live() -> int:
    raw = os.environ.get("VALYQON_RU_EIS_CA_CERT", "")
    if not raw or not Path(raw).is_file():
        print("EIS_TRANSPORT_DIAGNOSTIC=BLOCKED_NO_CA")
        return 2
    try:
        verify_root(Path(raw).read_bytes())
    except (ValueError, OSError, UnicodeError):
        print("EIS_TRANSPORT_DIAGNOSTIC=BLOCKED_CA_PIN")
        return 2
    # All paths are built by the existing official adapters, never operator input.
    for label, url in TARGETS.items():
        try:
            with httpx.Client(
                timeout=12, verify=raw, trust_env=False, follow_redirects=False
            ) as client:
                # Stream only response headers. Don't download or print notice bodies.
                with client.stream("GET", url) as response:
                    verdict = classify(
                        response.status_code, response.headers.get("Content-Type", ""), label
                    )
        except httpx.ConnectTimeout:
            verdict = "CONNECT_TIMEOUT"
        except httpx.ReadTimeout:
            verdict = "READ_TIMEOUT"
        except httpx.ConnectError:
            verdict = "CONNECT_OR_TLS_FAILURE"
        except httpx.HTTPError:
            verdict = "HTTPX_TRANSPORT_FAILURE"
        except (ValueError, OSError):
            verdict = "NETWORK_OR_POLICY_FAILURE"
        print(label + "_TRANSPORT=" + verdict, flush=True)
    print("EIS_TRANSPORT_DIAGNOSTIC=COMPLETE_NOT_SOURCE_PROOF")
    print("PRODUCTION_CHANGED=NO; TELEGRAM_SEND=NO")
    return 0


def self_test() -> None:
    assert len(TARGETS) == 3
    assert all(u.startswith("https://zakupki.gov.ru/") for u in TARGETS.values())
    assert classify(404, "text/html", "EIS_44_HTML") == "OFFICIAL_ROUTE_NOT_FOUND"
    assert classify(403, "text/html", "EIS_44_HTML") == "PUBLISHER_DENIED_OR_RATE_LIMITED"
    assert classify(200, "text/html", "EIS_44_HTML") == "HTTP_200_HTML_UNPARSED"
    assert classify(200, "text/html", "EIS_223_RSS") == "HTTP_200_UNEXPECTED_MEDIA_TYPE"
    print("EIS_TRANSPORT_SELF_TEST=PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument("--self-test", action="store_true")
    flags.add_argument("--live", action="store_true")
    options = parser.parse_args()
    if options.self_test:
        self_test()
        return 0
    return live()


if __name__ == "__main__":
    raise SystemExit(main())
