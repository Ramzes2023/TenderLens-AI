"""Public native NMCK small-purchase discovery; strict read-only live evidence.

Only first-party entries are accepted. The public catalog also syndicates
external SPEСTENDER cards; NEVER count/copy those as native NMCK notices.
This probe proves list->detail identity only, NOT SQL/tenant integration.
"""
from __future__ import annotations

import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit, parse_qsl

from app.sources.http import FetchPolicy, bounded_fetch, source_client, ConnectorTransportError

HOST = "xn--j1adc1b.xn--p1ai"
LIST_URL = f"https://{HOST}/procedures"
MAX_BYTES = 1_800_000
SLUG = re.compile(r"[a-z0-9-]{6,140}-(\d{11})m")
NUMBER = re.compile(r"№\s*(\d{11})\s*[МM]")
MAX_DETAILS = 2


class PublicHtml(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._current = None
        self.headings = []
        self._h1 = None
        self.visible = []
        self._hidden = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"style", "script", "svg", "template"}:
            self._hidden += 1
        if self._hidden:
            return
        if tag == "a":
            self._current = (attrs.get("href"), [])
        if tag == "h1":
            self._h1 = []

    def handle_data(self, data):
        if self._hidden:
            return
        self.visible.append(data)
        if self._current is not None:
            self._current[1].append(data)
        if self._h1 is not None:
            self._h1.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._current is not None:
            href, parts = self._current
            self.links.append((href, " ".join(" ".join(parts).split())))
            self._current = None
        if tag == "h1" and self._h1 is not None:
            self.headings.append(" ".join(" ".join(self._h1).split()))
            self._h1 = None
        if tag in {"style", "script", "svg", "template"} and self._hidden:
            self._hidden -= 1


def safe_slug(href: str):
    if type(href) is not str or not 0 < len(href) <= 500:
        return None
    if "\\" in href or any(ch.isspace() or ord(ch) < 32 for ch in href):
        return None
    try:
        p = urlsplit(urljoin(LIST_URL, href))
        if (p.scheme != "https" or p.netloc != HOST
                or p.username is not None or p.password is not None or p.port is not None
                or p.fragment or p.path.rstrip("/") != "/procedures"):
            return None
        q = parse_qsl(p.query, keep_blank_values=True)
        if len(q) != 1 or q[0][0] != "procedure":
            return None
        slug = q[0][1]
        return (slug, SLUG.fullmatch(slug).group(1)) if SLUG.fullmatch(slug) else None
    except ValueError:
        return None


def parse_list(data: bytes, *, limit=MAX_DETAILS):
    if type(data) is not bytes or not 0 < len(data) <= MAX_BYTES or b"\0" in data:
        raise ValueError("Invalid native NMCK listing")
    page = PublicHtml()
    page.feed(data.decode("utf-8-sig", "replace"))
    page.close()
    found, ids = [], set()
    for href, title in page.links:
        parsed = safe_slug(href)
        if parsed is None or not 5 <= len(title) <= 260:
            continue
        slug, num = parsed
        if num in ids:
            continue
        ids.add(num)
        # Rebuild a canonical, fixed-host official URL, NEVER follow the source href.
        found.append((slug, num, title, LIST_URL + "?procedure=" + slug))
        if len(found) >= limit:
            break
    if len(found) < limit:
        raise ValueError("Insufficient independently identifiable native NMCK notices")
    return found


def verify_detail(data: bytes, *, slug: str, identity: str, title: str):
    if type(data) is not bytes or not 0 < len(data) <= MAX_BYTES or b"\0" in data:
        raise ValueError("Invalid native NMCK detail")
    match = SLUG.fullmatch(slug)
    if match is None or identity != match.group(1):
        raise ValueError("Native NMCK detail identity malformed")
    doc = PublicHtml()
    doc.feed(data.decode("utf-8-sig", "replace"))
    doc.close()
    headings = [s for s in doc.headings if s]
    if len(headings) != 1 or not headings[0].casefold().startswith(title.casefold()):
        raise ValueError("Independent native NMCK detail title mismatch")
    # NMCK detail must display the same procurement number encoded in the
    # first-party slug. A matching title alone is not enough.
    visible = " ".join(" ".join(doc.visible).split())
    numbers = NUMBER.findall(visible)
    if identity not in numbers:
        raise ValueError("Independent native NMCK procurement number mismatch")
    return {"identity": identity, "title_confirmed": True, "number_confirmed": True}


async def live():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), MAX_DETAILS + 1, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=22, trust_env=False, follow_redirects=False,
            headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
        ) as client:
            listing = await client.get(LIST_URL)
            listing.raise_for_status()
            if "html" not in listing.headers.get("content-type", "").lower():
                raise ValueError("NMCK catalog is not public HTML")
            entries = parse_list(listing.content)
            verified = []
            for slug, identity, title, detail_url in entries:
                detail = await client.get(detail_url)
                detail.raise_for_status()
                if "html" not in detail.headers.get("content-type", "").lower():
                    raise ValueError("NMCK detail is not public HTML")
                verified.append(verify_detail(detail.content, slug=slug, identity=identity, title=title))
            return verified


def main():
    try:
        rows = asyncio.run(live())
    except (ConnectorTransportError, ValueError, OSError, TimeoutError) as exc:
        print("RU_NMCK_NATIVE_LIVE=BLOCKED_" + type(exc).__name__)
        if isinstance(exc, ConnectorTransportError):
            print("RU_NMCK_TRANSPORT_RETRYABLE=" + str(exc.retryable))
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_NMCK_INDEPENDENT_NATIVE_DETAIL_COUNT=" + str(len(rows)))
    print("RU_NMCK_NATIVE_LIVE=" + ("PASS_DISCOVERY_NOT_INTEGRATED" if len(rows) == MAX_DETAILS else "BLOCKED"))
    print("PRODUCTION_CHANGED=NO")
    return 0 if len(rows) == MAX_DETAILS else 2


if __name__ == "__main__":
    raise SystemExit(main())
