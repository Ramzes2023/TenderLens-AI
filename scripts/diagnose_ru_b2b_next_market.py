"""Read-only original B2B-Center alternate-market diagnostic, NOT tender acceptance.

The official legacy /search/ and /search/industry/ofis/ have intermittently
returned HTTP 502 / ReadTimeout from hosted runners. Investigate exactly one
other observed original HTTPS page. No fallback is activated in production.
No notice is persisted, scored, reported as accepted, or sent to Telegram.
"""
import asyncio
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from app.sources.http import (
    ConnectorTransportError, FetchPolicy, bounded_fetch, source_client,
)

NEXT_MARKET_URL = "https://www.b2b-center.ru/app/next/market-search/?from=0"
HOST = "www.b2b-center.ru"
MAX_BYTES = 2 * 1024 * 1024
MAX_ANCHORS = 10000


class OriginalNextLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchor_count = 0
        self.same_origin_links = 0
        self.native_links = set()
        self.native_path_candidates = set()
        self.same_origin_app_routes = 0
        self.with_query = 0

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        self.anchor_count += 1
        if self.anchor_count > MAX_ANCHORS:
            raise ValueError("Too many HTML anchors in bounded listing.")
        href = dict(attrs).get("href")
        if not href or any(ord(ch) < 33 or ord(ch) == 92 for ch in href):
            return
        try:
            url = urlsplit(urljoin(NEXT_MARKET_URL, href))
        except ValueError:
            return
        if (url.scheme != "https" or url.hostname != HOST or url.username or
                url.password or url.fragment or url.port not in (None, 443)):
            return
        self.same_origin_links += 1
        if url.path.startswith("/app/"):
            self.same_origin_app_routes += 1
        # Distinguish plausible original detail routes from actual safe
        # no-query accepted links, never use either as procurement evidence.
        if re.fullmatch(r"/app/market-next/[^/]{1,200}/tender-[0-9]{3,12}/", url.path):
            self.native_path_candidates.add(url.path)
            if url.query:
                self.with_query += 1
            else:
                self.native_links.add(url.path)


def analyze_official_html(payload: bytes):
    if not payload or len(payload) > MAX_BYTES:
        raise ValueError("Missing or oversized HTML.")
    parser = OriginalNextLinks()
    parser.feed(payload.decode("utf-8-sig", errors="strict"))
    parser.close()
    report = {"anchor_count": parser.anchor_count,
              "same_origin_href_count": parser.same_origin_links,
              "same_origin_app_route_count": parser.same_origin_app_routes,
              "first_party_native_detail_links": len(parser.native_links),
              "native_path_candidates": len(parser.native_path_candidates),
              "native_path_candidates_with_query": parser.with_query,
              "embedded_tender_id_markers": len(set(re.findall(rb"tender-[0-9]{4,12}", payload))),
              "html_bytes": len(payload)}
    # The current official frontend serves Vue SSR procedure cards: the
    # original /market/.../tender-N/ href includes a #btid analytics fragment
    # and is not covered by the old anchor-only diagnostic. Reuse the exact
    # production parser, and output counts only, NEVER notice content or URLs.
    from app.sources.b2b_next_market import parse_next_market
    from app.sources.eis_rss import SourceError
    # These codes are fixed by the strict first-party SSR parser, never
    # populated from arbitrary HTML text, URLs or exception details.
    codes = {
        "B2B-Center ambiguous SSR field.": "FIELD_CARDINALITY",
        "B2B-Center conflicting SSR identity.": "NATIVE_IDENTITY_CONFLICT",
        "B2B-Center ambiguous SSR publication date.": "PUBLICATION_DATE_CARDINALITY",
        "B2B-Center ambiguous SSR deadline.": "DEADLINE_CARDINALITY",
        "B2B-Center invalid SSR date.": "DATE_FORMAT",
        "B2B-Center unrecognized SSR price.": "PRICE_FORMAT",
        "B2B-Center invalid SSR price.": "PRICE_RANGE",
        "B2B-Center unsafe SSR URL.": "URL_PROVENANCE",
        "B2B-Center conflicting duplicate identity.": "DUPLICATE_IDENTITY",
        "B2B-Center returned no usable procurement records.": "NO_VERIFIED_NATIVE_RECORDS",
        "B2B-Center empty or oversized HTML.": "EMPTY_OR_OVERSIZED_HTML",
        "B2B-Center invalid HTML encoding.": "ENCODING",
        "Invalid normalized notice.": "NORMALIZED_NOTICE_CONTRACT",
    }
    try:
        verified = parse_next_market(payload, limit=10)
    except (SourceError, ValueError, TypeError, UnicodeError) as error:
        report["ssr_native_schema"] = "rejected"
        report["ssr_rejection_class"] = type(error).__name__
        # Unknown exceptions are only reported by *class*, never by message.
        report["ssr_rejection_code"] = (
            codes.get(str(error), "UNCLASSIFIED")
            if type(error) is SourceError else "UNCLASSIFIED"
        )
        report["ssr_verified_native_count"] = 0
    else:
        report["ssr_native_schema"] = "verified"
        report["ssr_verified_native_count"] = len(verified)
    return report


async def probe():
    try:
        policy = FetchPolicy(frozenset({HOST}), 1, max_bytes=MAX_BYTES)
        with bounded_fetch(policy):
            async with source_client(timeout=25, follow_redirects=False,
                                     trust_env=False, headers={"Accept": "text/html"}) as client:
                response = await client.get(NEXT_MARKET_URL)
        report = {"source": "b2b_center", "diagnostic_only": True,
                  "status": response.status_code,
                  "html_content_type": "text/html" in response.headers.get("content-type", "").lower(),
                  "request_count": policy.requests, "tls_policy": "strict",
                  "new_source_enabled": False}
        if response.status_code != 200 or not report["html_content_type"]:
            return report
        report.update(analyze_official_html(response.content))
        return report
    except ConnectorTransportError as error:
        return {"source": "b2b_center", "diagnostic_only": True,
                "transport_error_class": type(error).__name__,
                "reason": error.reason, "retryable": error.retryable,
                "new_source_enabled": False}
    except (ValueError, UnicodeError, OSError) as error:
        return {"source": "b2b_center", "diagnostic_only": True,
                "safe_error_class": type(error).__name__,
                "new_source_enabled": False}


def main():
    report = asyncio.run(probe())
    print("B2B_NEXT_MARKET_DIAG=" + json.dumps(report, sort_keys=True), flush=True)
    # This diagnostic is never sufficient for Worker→SQL or authenticated scoring.
    return 0 if (report.get("status") == 200
                 and report.get("html_content_type")
                 and report.get("ssr_verified_native_count", 0) >= 1) else 1


if __name__ == "__main__":
    raise SystemExit(main())
