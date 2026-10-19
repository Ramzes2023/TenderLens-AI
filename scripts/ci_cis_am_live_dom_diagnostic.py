"""Read-only official Armenian ARMEPS HTML-shape diagnosis.

No fake acceptance; never output upstream HTML, tender content, or cookies.
Target stays pinned to HTTPS ARMEPS with project transport protections.
"""
import asyncio
import json
import re
import ssl

import httpx

from app.sources.am_armeps import (
    ARMEPS_LISTING_URL, _Tables, parse_armeps_listing, _retryable_official_dns_failure,
    observed_next_page,
)
from app.sources.http import (
    ConnectorTransportError, FetchPolicy, _is_public_ip_error,
    bounded_fetch, source_client,
)


def _retryable_observed_timeout(error):
    """Only a proved connect/read timeout can retry; never TLS, IP or policy errors."""
    if (not isinstance(error, ConnectorTransportError) or
            not error.retryable or _is_public_ip_error(error)):
        return False
    current, seen, timed_out = error.__cause__, set(), False
    while isinstance(current, BaseException) and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ssl.SSLError):
            return False
        if isinstance(current, (httpx.ConnectTimeout, httpx.ReadTimeout)):
            timed_out = True
        current = current.__cause__
    return timed_out


async def _fetch_bounded_first_page():
    """Up to three independent STRICT official HTTPS attempts; require real response."""
    for attempt in range(1, 4):
        try:
            # Each attempt gets a fresh one-request policy, exact original host,
            # TLS verification, public-IP/peer validation and 1 MiB hard limit.
            with bounded_fetch(FetchPolicy(
                frozenset({"eauction.armeps.am"}), 1, max_bytes=1024 * 1024
            )):
                async with source_client(
                    timeout=15.0, trust_env=False, follow_redirects=False
                ) as client:
                    response = await client.get(ARMEPS_LISTING_URL)
            return response, attempt
        except ConnectorTransportError as error:
            if attempt == 3 or not _retryable_observed_timeout(error):
                raise
            await asyncio.sleep(attempt)
    raise AssertionError("ARMEPS bounded official attempt count exhausted.")


async def run():
    try:
        resp, attempts = await _fetch_bounded_first_page()
    except Exception as error:
        chain, seen = [], set()
        current = error
        while isinstance(current, BaseException) and id(current) not in seen and len(chain) < 7:
            seen.add(id(current))
            chain.append({"type": type(current).__name__,
                          "module": type(current).__module__,
                          "audited_dns_failed": type(current).__name__ == "ConnectError"
                          and str(current) == "DNS resolution failed",
                          "tls_error": "SSL" in type(current).__name__,
                          "safe_network_kind": (
                              "dns" if str(current) == "DNS resolution failed"
                              else "tcp" if str(current) == "TCP connection failed"
                              else "timeout" if "timeout" in type(current).__name__.lower()
                              else "other")})
            current = current.__cause__
        print(json.dumps({"source": "am_armeps", "upstream_html_retrieved": False,
                          "exception_chain_types": chain,
                          "classified_retryable_dns": _retryable_official_dns_failure(error)}, sort_keys=True))
        return 1
    report = {
        "network_attempts": attempts,
        "status": resp.status_code,
        "html_content_type": "html" in resp.headers.get("content-type", "").lower(),
        "html_bytes": len(resp.content),
        "observed_page_two": observed_next_page(resp.text, 1) is not None,
    }
    if resp.status_code != 200 or not report["html_content_type"]:
        print(json.dumps(report, sort_keys=True))
        return 1
    parser = _Tables()
    try:
        parser.feed(resp.text)
        report["tables"] = len(parser.tables)
        report["headers"] = [[re.sub("[^a-z]", "", cell.casefold()) for cell in table[0]][:10]
                             for table in parser.tables if table][:5]
        report["row_shapes"] = [
            {"rows": len(table), "row_sizes": sorted(set(len(row) for row in table)),
             "detail_anchor_positions": sorted(set(pos for row in table[1:6] for pos, href in parser.links.get(id(row), []))),
             "detail_link_count_first5": [len(parser.links.get(id(row), [])) for row in table[1:6]]}
            for table in parser.tables[:5]]
    except Exception as exc:
        report["parser_error"] = type(exc).__name__
        report["parser_reason"] = str(exc)[:120]
    try:
        notices = parse_armeps_listing(resp.text)
        report["accepted"] = len(notices)
    except Exception as exc:
        report["normalization_error"] = type(exc).__name__
        report["normalization_reason"] = str(exc)[:120]
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("accepted", 0) >= 3 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
