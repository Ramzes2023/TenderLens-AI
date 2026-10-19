"""One strictly verified EIS request with system roots or a pinned scoped CA.

Operator Windows system-store trust is a separate, unproven environment.
This script never relaxes certificates, redirects, network policy or identity.
"""
from __future__ import annotations

import asyncio
import json
import ssl
import platform
import argparse
from pathlib import Path
from scripts.ru_transport_diagnostics import transport_failure

from app.sources.eis_rss import (
    SourceError, build_eis_rss_url, parse_eis_feed, verify_eis_feed_law,
    EIS_USER_AGENT,
)
from scripts.ru_eis_pinned_tls_probe import pinned_ssl_context
from app.sources.http import FetchPolicy, bounded_fetch, source_client


async def run(root_file: Path | None = None):
    status = {"state": "BLOCKED", "http_status": None, "records": 0,
              "error_type": None, "strict_tls": True, "hostname_check": True,
              "platform": platform.system()}
    context = pinned_ssl_context(root_file) if root_file else ssl.create_default_context()
    status["trust_source"] = "verified_pinned_root" if root_file else "system"
    status["strict_tls"] = context.verify_mode == ssl.CERT_REQUIRED
    status["hostname_check"] = context.check_hostname
    if not status["strict_tls"] or not status["hostname_check"]:
        status["state"] = "INVALID_CA_CONFIGURATION"
        return status

    async def capture(response):
        status["http_status"] = response.status_code

    try:
        with bounded_fetch(FetchPolicy(frozenset({"zakupki.gov.ru"}), 1,
                                       max_bytes=5 * 1024 * 1024)):
            async with source_client(
                verify=context, trust_env=False, follow_redirects=False,
                timeout=12, event_hooks={"response": [capture]},
                headers={"User-Agent": EIS_USER_AGENT},
            ) as client:
                response = await asyncio.wait_for(
                    client.get(build_eis_rss_url("поставка")), timeout=18)
                response.raise_for_status()
                verify_eis_feed_law(response.content, "44-FZ")
                status["records"] = len(parse_eis_feed(response.content))
                status["state"] = (
                    "PUBLIC_LAW_VERIFIED_NOTICE_FEED" if status["records"]
                    else "EMPTY_OR_UNVERIFIED"
                )
    except Exception as error:
        status["error_type"] = type(error).__name__
        status["transport_failure"] = transport_failure(error)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pinned-root", type=Path)
    args = parser.parse_args()
    print("RU_EIS_SYSTEM_CA=" + json.dumps(
        asyncio.run(run(args.pinned_root)), ensure_ascii=False, separators=(",", ":"
    )), flush=True)
    print("WINDOWS_CA_VERIFIED=NO")
    print("NO_TLS_VERIFICATION_BYPASS=YES")
    print("PRODUCTION_CHANGED=NO")


if __name__ == "__main__":
    main()
