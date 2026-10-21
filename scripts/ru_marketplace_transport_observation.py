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


def classify_redirect(location, listing_url):
    """No redirect following: classify *only* an allowed HTTP Location.

    Never log URLs, query parameters, tokens, or user-provided hostnames.
    A 3xx is NOT an accepted tender, even for safe canonical redirects.
    """
    if type(location) is not str or not 0 < len(location) <= 2000:
        return "MISSING_OR_INVALID"
    if any(ord(char) < 33 or ord(char) == 127 or char == "\\" for char in location):
        return "INVALID"
    try:
        target = urlsplit(urljoin(listing_url, location))
        original = urlsplit(listing_url)
        if (target.scheme != "https" or target.netloc != original.netloc
                or target.username or target.password
                or target.query or target.fragment or target.port is not None):
            return "NOT_PUBLIC_CANONICAL"
        if target.path == original.path:
            return "SAME_PATH"
        if target.path == original.path.rstrip("/") + "/":
            return "TRAILING_SLASH_ONLY"
        if any(word in target.path.lower() for word in
               ("/login", "/auth", "/account", "/captcha", "/signin", "/register")):
            return "AUTH_OR_CHALLENGE"
        return "DIFFERENT_SAME_ORIGIN_PATH"
    except ValueError:
        return "INVALID"


async def probe(source):
    module = TARGETS[source]
    result = {"source": source, "http_status": None, "verified_ingestion": False}
    async def observed(response):
        result["http_status"] = response.status_code
        if response.status_code in (301, 302, 303, 307, 308):
            result["redirect_class"] = classify_redirect(
                response.headers.get("location"), module.LIST_URL,
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
