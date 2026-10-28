"""Compare ONLY publicly documented first-party Fabrikant published-list URLs.

Earlier region-filtered `placer_search_str=...` requests failed with network or
HTTP non-2xx while separate soap4 individual originals were verified. This
probe isolates plain published-list reachability from the query filters.

These routes are backed by first-party published index references:
 /44/catalog/procedure/published
 /44/catalog/procedure/published?dir=desc&order=publication_datetime

This is READ-ONLY research. Passing HTTP 200 alone never proves tender identity
or freshness. No alternative hosts, search indexes as a source, credentials,
third-party proxies, cookies, redirect following, TLS weakening, database
writes, or production operations.
"""
from __future__ import annotations

import asyncio
import json
from html.parser import HTMLParser

from app.sources.http import (
    ConnectorTransportError, FetchPolicy, bounded_fetch, source_client,
)
from scripts.research_ru_fabrikant_published_regional_routes import (
    HOSTS, PATH, MAX_BYTES, official_list_ids, safe_category,
)

# Both exact query variants have been observed on genuine public publisher
# pages. Do not generate arbitrary pagination/search URLs here.
SUFFIXES = ("", "?dir=desc&order=publication_datetime")
CURRENT_CONFIRMED_DETAILS = frozenset({
    "0114500000826002518",    # Ingushetia
    "0194200000526005756",    # Chechnya
    "0194200000526005775",    # Chechnya
})


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript", "svg"}:
            self.hidden.append(tag)

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()

    def handle_data(self, text):
        if not self.hidden:
            self.text.append(text)


def classify_publisher_html(body: bytes, *, host: str) -> dict[str, object]:
    ids = official_list_ids(body, host)
    visible = VisibleText()
    visible.feed(body.decode("utf-8-sig", "replace"))
    visible.close()
    content = " ".join(" ".join(visible.text).casefold().split())
    # A portal login or captcha page must never be mistaken for a native
    # published register, even if it embeds navigation and an old link.
    if any(term in content for term in (
        "пожалуйста, войдите", "необходимо авторизоваться", "captcha",
        "подтвердите, что вы не робот", "введите капчу",
    )):
        return {"category": "official_login_or_challenge",
                "firstparty_anchor_count": 0, "known_current_ids": 0}
    return {
        "category": (
            "firstparty_published_anchor_candidates" if ids
            else "firstparty_published_html_without_anchors"
        ),
        "firstparty_anchor_count": len(ids),
        "known_current_ids": len(ids & CURRENT_CONFIRMED_DETAILS),
    }


async def inspect() -> list[dict[str, object]]:
    results = []
    with bounded_fetch(FetchPolicy(
        frozenset(HOSTS), len(HOSTS) * len(SUFFIXES), max_bytes=MAX_BYTES,
    )):
        async with source_client(
            timeout=25, trust_env=False, follow_redirects=False,
            headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
        ) as client:
            for host in HOSTS:
                for variant, suffix in enumerate(SUFFIXES):
                    stage = "PUBLIC_PUBLISHED_LIST_GET"
                    try:
                        reply = await client.get(f"https://{host}{PATH}{suffix}")
                        reply.raise_for_status()
                        if "html" not in reply.headers.get(
                            "content-type", "").casefold():
                            raise ValueError("Not first-party HTML")
                        observed = classify_publisher_html(reply.content, host=host)
                        results.append({
                            "publisher_host": host, "variant": variant,
                            **observed,
                        })
                    except (ConnectorTransportError, ValueError) as exc:
                        results.append({
                            "publisher_host": host, "variant": variant,
                            "category": safe_category(exc),
                            "firstparty_anchor_count": 0, "known_current_ids": 0,
                        })
                    except Exception:
                        results.append({
                            "publisher_host": host, "variant": variant,
                            "category": "unclassified",
                            "firstparty_anchor_count": 0, "known_current_ids": 0,
                        })
    return results


def main() -> int:
    for row in asyncio.run(inspect()):
        print("FABRIKANT_UNFILTERED_PUBLISHED=" + json.dumps(
            row, sort_keys=True))
    print("REGION_SCOPED_AUTOMATIC_DISCOVERY=NOT_PROVED")
    print("ACTUAL_WORKER_SQL_GUEST=NOT_PROVED")
    print("PUBLISHER_MIRRORS_COUNTED_SEPARATELY=NO")
    print("PRODUCTION_CHANGED=NO")
    print("RELEASE_READY=NO")
    return 0  # Diagnostics MUST NOT greenlight production ingestion.


if __name__ == "__main__":
    raise SystemExit(main())
