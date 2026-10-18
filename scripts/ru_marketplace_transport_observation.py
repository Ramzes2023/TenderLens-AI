"""One bounded public listing request; numeric HTTP evidence, never bodies/headers."""
import argparse
import asyncio
import json
from urllib.parse import urljoin, urlsplit
from app.sources import gpb_etp_public, tektorg_public_html, fabrikant_44_public, roseltorg_public
from app.sources.http import FetchPolicy, bounded_fetch, source_client

TARGETS = {m.SOURCE_ID: m for m in (
    gpb_etp_public, tektorg_public_html, fabrikant_44_public, roseltorg_public,
)}


def safe_redirect_class(location, *, host, listing_url):
    """Only structural observations; never log a Location or untrusted values."""
    if type(location) is not str or not 0 < len(location) <= 1600:
        return "ABSENT_OR_OVERSIZED"
    if any(ord(c) < 33 or ord(c) == 127 for c in location):
        return "INVALID"
    try:
        p = urlsplit(urljoin(listing_url, location))
        listing = urlsplit(listing_url)
        if (p.scheme != "https" or p.netloc != host or p.username is not None
                or p.password is not None or p.port is not None
                or p.query or p.fragment):
            return "NONCANONICAL_OR_CROSS_ORIGIN"
        if p.path == listing.path:
            return "SAME_LISTING"
        if p.path.rstrip("/") == listing.path.rstrip("/"):
            return "SAME_LISTING_SLASH_VARIANT"
        return "SAME_HOST_OTHER_PATH"
    except ValueError:
        return "INVALID"



async def probe(source):
    module = TARGETS[source]
    result = {"source": source, "http_status": None, "verified_ingestion": False}
    async def observed(response):
        result["http_status"] = response.status_code
        if response.status_code in (301, 302, 303, 307, 308):
            result["redirect_class"] = safe_redirect_class(
                response.headers.get("location"),
                host=module.HOST, listing_url=module.LIST_URL,
            )
    try:
        with bounded_fetch(FetchPolicy(frozenset({module.HOST}), 1, max_bytes=module.MAX_BYTES)):
            async with source_client(
                timeout=25, follow_redirects=False, trust_env=False,
                headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
                event_hooks={"response": [observed]},
            ) as client:
                response = await client.get(module.LIST_URL)
                result["bytes"] = len(response.content)
                result["html"] = "html" in response.headers.get("content-type", "").lower()
    except Exception as error:
        result["error_class"] = type(error).__name__
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=sorted(TARGETS))
    args = parser.parse_args()
    result = asyncio.run(probe(args.source))
    print("RU_LIST_TRANSPORT=" + json.dumps(result, sort_keys=True))
    # Observation only: caller MUST also run strict original/worker acceptance.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
