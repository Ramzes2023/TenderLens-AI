"""Independent official Gazprombank ETP RSS -> original detail research.

Official docs advertise /procedures.rss on new.etpgpb.ru. Fail closed
unless RSS *itself* yields at least two distinct original linked procedures,
which independently pass the already merged GPB detail validator.
No changes to production/catalog, tokens, proxies, redirects or TLS.
"""
from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

import httpx
from app.sources.http import (
    FetchPolicy, bounded_fetch, source_client, ConnectorTransportError,
)
from app.sources.gpb_etp_public import parse_gpb_verified_detail

FEED_HOST = "new.etpgpb.ru"
DETAIL_HOST = "etpgpb.ru"
FEED = "https://new.etpgpb.ru/procedures.rss"
MAX_BYTES = 1_800_000
MIN_ORIGINALS = 2
ORIGINAL_PATH = re.compile(r"/procedures/etp/([0-9]{5,10})-[a-z0-9-]+/")


def feed_originals(body):
    if type(body) is not bytes or not 0 < len(body) <= MAX_BYTES:
        raise ValueError("Invalid official GPB feed")
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ValueError("GPB RSS XML entities forbidden")
    root = ET.fromstring(body)
    if root.tag != "rss":
        raise ValueError("Expected genuine RSS root")
    channel = root.find("channel")
    if channel is None:
        raise ValueError("Expected RSS channel")
    entries, identities = [], {}
    for item in channel.findall("item"):
        url = (item.findtext("link") or "").strip()
        title = " ".join((item.findtext("title") or "").split())
        if not 8 <= len(title) <= 1000:
            continue
        parsed = urlsplit(url)
        found = ORIGINAL_PATH.fullmatch(parsed.path)
        if (not found or parsed.scheme != "https" or parsed.netloc != DETAIL_HOST
                or parsed.query or parsed.fragment
                or parsed.username is not None or parsed.password is not None
                or parsed.port is not None):
            continue
        identity = found.group(1)
        if identity in identities:
            if identities[identity] != url:
                raise ValueError("Contradictory original GPB RSS notice identity")
            continue
        identities[identity] = url
        entries.append((identity, title, url))
    if len(entries) < MIN_ORIGINALS:
        raise ValueError("No two genuine original first-party GPB RSS detail URLs")
    return entries[:MIN_ORIGINALS]


async def real():
    with bounded_fetch(FetchPolicy(
        frozenset({FEED_HOST, DETAIL_HOST}), MIN_ORIGINALS + 1,
        max_bytes=MAX_BYTES,
    )):
        async with source_client(
            timeout=25, trust_env=False, follow_redirects=False,
            headers={"Accept": "application/rss+xml, application/xml, text/xml",
                     "User-Agent": "Mozilla/5.0"},
        ) as client:
            feed = await client.get(FEED)
            feed.raise_for_status()
            media = feed.headers.get("content-type", "").lower()
            if not any(k in media for k in ("xml", "rss")):
                raise ValueError("Official feed was not RSS/XML")
            original = feed_originals(feed.content)
            checked = []
            for identity, title, url in original:
                detail = await client.get(url)
                detail.raise_for_status()
                if "html" not in detail.headers.get("content-type", "").lower():
                    raise ValueError("Original GPB detail not HTML")
                n = parse_gpb_verified_detail(detail.content, identity, url)
                if n.external_id != identity or n.source != "gpb_etp_public":
                    raise ValueError("Original GPB detail identity not corroborated")
                checked.append(n)
            if len({n.external_id for n in checked}) != MIN_ORIGINALS:
                raise ValueError("GPB original RSS details not distinct")
            return checked


def main():
    try:
        notices = asyncio.run(real())
        print("RU_GPB_DOCUMENTED_RSS_VERIFIED_ORIGINALS=" + str(len(notices)))
        print("RU_GPB_DOCUMENTED_RSS=PASS_RESEARCH_ONLY")
        code = 0 if len(notices) == MIN_ORIGINALS else 2
    except (ValueError, ET.ParseError, ConnectorTransportError, httpx.HTTPError,
            OSError, TimeoutError) as error:
        print("RU_GPB_DOCUMENTED_RSS=BLOCKED_" + type(error).__name__)
        if isinstance(error, ConnectorTransportError):
            print("RU_GPB_RSS_RETRYABLE=" + str(error.retryable))
        code = 2
    print("PRODUCTION_CHANGED=NO")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
