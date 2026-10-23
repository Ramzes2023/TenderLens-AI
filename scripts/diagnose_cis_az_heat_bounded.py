"""Read-only first-party AZ tender card health probe; NEVER release evidence.

No IDs, titles, response bodies, URLs, cookies or credentials are logged.
Validating a card here cannot replace real leased Worker/SQL acceptance.
"""
import asyncio
import json

import httpx

from app.sources.az_azeristilik import (
    HOST, INDEX_URL, MAX_BODY, MAX_DETAILS, AzerbaijanHeatSource,
    discover_official_posts, parse_public_detail,
)
from app.sources.eis_rss import SourceError
from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client


async def examine():
    result = {"source": "az_azeristilik", "diagnostic_only": True,
              "saved_or_sent": False, "index_confirmed": False,
              "checked_cards": 0, "verified_cards": 0,
              "excluded_http_status": {}, "rejected_schema": 0}
    policy = FetchPolicy(frozenset({HOST}), 1 + MAX_DETAILS,
                         max_bytes=MAX_BODY,
                         allowed_http_errors=frozenset({403, 404, 410}))
    try:
        with bounded_fetch(policy):
            async with source_client(timeout=12, trust_env=False,
                                     follow_redirects=False,
                                     headers={"Accept": "text/html"}) as client:
                index = await client.get(INDEX_URL)
                index.raise_for_status()
                if "html" not in index.headers.get("content-type", "").lower():
                    raise SourceError("Invalid official index content type.")
                links = discover_official_posts(index.text)
                result["index_confirmed"] = True
                result["discovered_cards"] = len(links)
                for url, title in links[:MAX_DETAILS]:
                    result["checked_cards"] += 1
                    try:
                        response = await client.get(url)
                        if response.status_code in (403, 404, 410):
                            key = str(response.status_code)
                            result["excluded_http_status"][key] = (
                                result["excluded_http_status"].get(key, 0) + 1
                            )
                            continue
                        response.raise_for_status()
                        if "html" not in response.headers.get("content-type", "").lower():
                            result["rejected_schema"] += 1
                            continue
                        parse_public_detail(response.text, url=url, listed_title=title)
                        result["verified_cards"] += 1
                    except SourceError:
                        result["rejected_schema"] += 1
                    except ConnectorTransportError as error:
                        result["failed_stage"] = "detail_transport"
                        result["transport_reason"] = error.reason
                        result["transport_retryable"] = error.retryable
                        break
    except httpx.HTTPStatusError as error:
        result["failed_stage"] = "index_http_status"
        result["index_http_status"] = error.response.status_code
    except ConnectorTransportError as error:
        result["failed_stage"] = result.get("failed_stage", "index_transport")
        result["transport_reason"] = error.reason
        result["transport_retryable"] = error.retryable
    except (SourceError, ValueError, UnicodeError):
        result["failed_stage"] = "index_or_schema"
    result["requests"] = policy.requests
    return result


def main():
    report = asyncio.run(examine())
    print("AZ_BOUNDED_FIRST_PARTY_DIAG=" + json.dumps(report, sort_keys=True),
          flush=True)
    # Diagnostics intentionally never indicate a source release PASS.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
