"""Research: public grid's anonymous anti-CSRF form + first-party read-only POST.

Not authentication bypass. GET openly published NoticesGrid and use only the
anonymous CSRF token/ephemeral same-origin session issued to that public page.
Do NOT log/copy cookies or tokens, follow redirects, use proxies, persist or
enable a source, or send POST to any endpoint other than its published grid.
"""
from __future__ import annotations

import asyncio
from html.parser import HTMLParser
import re

import httpx

from app.sources.http import (
    ConnectorTransportError, FetchPolicy, bounded_fetch, source_client,
)
from scripts.research_ru_dagestan_anonymous_post import (
    HOST, INDEX, URL, MAX_BYTES, FORM, published_route, parse_public_json,
)

TOKEN = re.compile(r"^[A-Za-z0-9+/_=.~-]{12,2048}$")


class AnonymousPublicGridFilter(HTMLParser):
    """Collect only public grid_filter input names, and its anti-CSRF value."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[bool] = []
        self.tokens: list[str] = []
        self.names: set[str] = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "div":
            parent = self.stack[-1] if self.stack else False
            css = (values.get("class") or "").split()
            self.stack.append(parent or ("grid_filter" in css))
        if tag == "input" and self.stack and self.stack[-1]:
            name = values.get("name")
            if name and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,69}", name):
                self.names.add(name)
            if name == "__RequestVerificationToken":
                token = values.get("value")
                if isinstance(token, str):
                    self.tokens.append(token)

    def handle_endtag(self, tag):
        if tag == "div" and self.stack:
            self.stack.pop()


def public_grid_token(html: bytes):
    if not published_route(html):
        raise ValueError("Unadvertised first-party public grid")
    form = AnonymousPublicGridFilter()
    form.feed(html.decode("utf-8-sig", "replace"))
    form.close()
    if len(form.tokens) != 1 or not TOKEN.fullmatch(form.tokens[0]):
        raise ValueError("No unambiguous public grid anti-forgery token")
    return form.tokens[0], sorted(form.names)


async def probe():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 2, max_bytes=MAX_BYTES)):
        # The anonymous browser first gets its public filter form and a matching
        # ephemeral same-origin anti-CSRF cookie. No login or user supplied data.
        async with source_client(
            timeout=24,
            trust_env=False,
            follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            index = await client.get(INDEX, headers={"Accept": "text/html"})
            if "html" not in index.headers.get("content-type", "").lower():
                raise ValueError("Original official grid not public HTML")
            token, field_names = public_grid_token(index.content)
            print("RU_DAG_GRID_PUBLIC_FILTER_NAMES=" + ",".join(field_names[:40]))
            # Do not log or export csrf token/cookie, even on failures.
            data = dict(FORM)
            data["__RequestVerificationToken"] = token
            response = await client.post(
                URL,
                headers={
                    "Accept": "application/json, text/javascript",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": INDEX,
                },
                data=data,
            )
            count, keys, shapes = parse_public_json(
                response.content, response.headers.get("content-type", ""),
            )
            print("RU_DAG_GRID_ANON_CSRF_ROWS=" + str(count))
            print("RU_DAG_GRID_ANON_CSRF_KEYS=" + ",".join(keys))
            print("RU_DAG_GRID_ANON_CSRF_SHAPES=" +
                  ",".join(shape for shape, _ in shapes))
            print("RU_DAG_ANON_CSRF=PUBLIC_SCHEMA_ONLY")
            print("REAL_ORIGINAL_DETAILS_VERIFIED=NO")
            print("WORKER_SQL_KEYWORD_TENANT_VERIFIED=NO")
            return 0


def main():
    try:
        return asyncio.run(probe())
    except (ValueError, ConnectorTransportError, httpx.HTTPError,
            OSError, TimeoutError) as e:
        print("RU_DAG_ANON_CSRF=BLOCKED_" + type(e).__name__)
        if isinstance(e, ConnectorTransportError):
            print("RU_DAG_RETRYABLE=" + str(e.retryable))
        return 2
    finally:
        print("PRODUCTION_CHANGED=NO")


if __name__ == "__main__":
    raise SystemExit(main())
