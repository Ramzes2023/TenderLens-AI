"""Read-only bounded first-party ADIF audit. Never enables sources or sends data.

Only aggregate counts and code-controlled failure categories are emitted.
No HTML, notice titles, doc links, credentials or customer information.
"""
import asyncio
import json

from app.sources.az_adif_small import HOST, MAX_BYTES, URL, Articles, BUYER, PUBLISHED, parse_public_articles
from app.sources.http import FetchPolicy, bounded_fetch, source_client, ConnectorTransportError
from app.sources.eis_rss import SourceError


async def examine():
    evidence = {"source": "az_adif_small", "diagnostic_only": True, "verified_live_worker": False}
    seen = {}
    async def note(response):
        seen["official_http_status"] = response.status_code

    policy = FetchPolicy(frozenset({HOST}), 1, max_bytes=MAX_BYTES)
    try:
        with bounded_fetch(policy):
            async with source_client(timeout=15, trust_env=False, follow_redirects=False,
                                     event_hooks={"response": [note]}) as client:
                response = await client.get(URL)
                response.raise_for_status()
                evidence["html_content_type"] = "html" in response.headers.get("content-type", "").lower()
                if evidence["html_content_type"]:
                    html = response.text
                    reader = Articles()
                    reader.feed(html)
                    reader.close()
                    evidence["article_count"] = len(reader.items)
                    evidence["buyer_title_articles"] = sum(
                        any(BUYER.casefold() in p.casefold()
                            and "kotirovka sorğusu elan edir" in p.casefold()
                            for p in item["paragraphs"]) for item in reader.items
                    )
                    evidence["dated_articles"] = sum(
                        any(PUBLISHED.fullmatch(p) for p in item["paragraphs"])
                        for item in reader.items
                    )
                    try:
                        rows = parse_public_articles(html)
                    except SourceError as error:
                        known = {
                            "AZ ADIF no verified dated official procurement announcements.": "NO_DATED_PUBLICATIONS",
                            "AZ ADIF public procurement article structure changed.": "ARTICLE_LAYOUT",
                            "AZ ADIF malformed or oversized official HTML.": "HTML_FORMAT",
                            "AZ ADIF missing unique original tender specification.": "SPEC_ORIGIN",
                        }
                        evidence["parser"] = "rejected"
                        evidence["parser_reason"] = known.get(str(error), "OTHER_CONTRACT")
                    else:
                        evidence["parser"] = "verified"
                        evidence["active_verified_quotations"] = len(rows)
    except ConnectorTransportError as error:
        evidence["transport_reason"] = error.reason
        evidence["transport_retryable"] = error.retryable
    except (SourceError, ValueError, UnicodeError):
        evidence["source_contract"] = "rejected"
    evidence.update(seen)
    evidence["request_count"] = policy.requests
    return evidence


def main():
    print("AZ_ADIF_DIAGNOSTIC=" + json.dumps(asyncio.run(examine()), sort_keys=True))
    return 0  # Diagnostic is never the release gate.


if __name__ == "__main__":
    raise SystemExit(main())
