"""Research-only direct first-party Dagestan native JSON list fetch, no browser.

JSON request envelope/field names and public pagination are independently
observed from official anonymous Chromium grid. No guessed auth endpoint,
proxy, cookies exported, insecure TLS, redirects or production writes.
Real list cards are NEVER equivalent to verified original detail pages.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urlsplit, urljoin
import httpx

from app.sources.http import FetchPolicy, bounded_fetch, source_client, ConnectorTransportError
from scripts.research_ru_dagestan_anonymous_post import (
    HOST, INDEX, URL, MAX_BYTES, published_route,
)

SORT_LIST = {
    "pub_date": "Дата публикации",
    "number": "Рег. номер",
    "name": "Наименование",
    "summa": "НМЦК",
    "uchr_sname": "Заказчик",
    "collecting_endDate": "Дата окончания подачи заявок",
}
DETAIL = re.compile(r"/smallpurchases/GzwSP/([0-9]{6,12})")


def settings(filter_value):
    if filter_value is not None and (type(filter_value) is not str or filter_value):
        raise ValueError("Only empty/null native public date filtering permitted")
    return {
        "page": 0, "rp": 10, "totalRows": 0, "sortField": "pub_date",
        "sortDir": "desc", "filter": {"dtDatePubBegin": filter_value},
        "sortList": SORT_LIST, "rpList": [10, 20, 30], "localFilter": [],
    }


def real_list_proof(data):
    if type(data) is not dict:
        raise ValueError("Native public JSON root missing")
    if type(data.get("items")) is not list or not 2 <= len(data["items"]) <= 10:
        raise ValueError("No two native public listing items")
    if type(data.get("totalRows")) is not int or data["totalRows"] < 2:
        raise ValueError("Native public listing total count invalid")
    verified = []
    for item in data["items"][:2]:
        if type(item) is not dict:
            raise ValueError("Native public item shape invalid")
        def nonempty(key, length=1400):
            value = item.get(key)
            if type(value) is not str or not 2 <= len(value.strip()) <= length:
                raise ValueError("Native public field missing: " + key)
            if "\x00" in value or re.search(r"<\s*[A-Za-z][^>]*>", value):
                raise ValueError("Native public field malformed: " + key)
            return value.strip()
        title = nonempty("name")
        buyer = nonempty("uchr_sname")
        number = nonempty("number", 250)
        raw_link = nonempty("link", 1800)
        p = urlsplit(urljoin(INDEX, raw_link))
        match = DETAIL.fullmatch(p.path)
        if (p.scheme != "https" or p.hostname != HOST or p.port not in (None, 443)
                or p.username or p.password or p.fragment or p.query or not match):
            raise ValueError("Noncanonical public Dagestan native detail path")
        if not number or not title or not buyer:
            raise ValueError("Empty published original data")
        verified.append((match.group(1), number))
    if len({a for a, _ in verified}) != 2 or len({b for _, b in verified}) != 2:
        raise ValueError("Repeated original public listing identity")
    return verified


async def probe():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 4, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=24, trust_env=False, follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            try:
                home = await client.get(INDEX, headers={"Accept": "text/html"})
            except ConnectorTransportError as err:
                print("RU_DAG_JSON_NATIVE_BLOCKED_AT=GET_PUBLIC_GRID")
                print("RU_DAG_JSON_NATIVE_RETRYABLE=" + str(err.retryable))
                raise
            if "html" not in home.headers.get("content-type", "").lower() or not published_route(home.content):
                raise ValueError("Official native list route not published")
            for i, filter_value in enumerate(("", None), 1):
                try:
                    response = await client.post(
                        URL, json={"settings": settings(filter_value)}, headers={
                            "Accept": "application/json, text/javascript",
                            "X-Requested-With": "XMLHttpRequest",
                            "Referer": INDEX,
                        },
                    )
                except ConnectorTransportError as err:
                    print("RU_DAG_JSON_NATIVE_BLOCKED_AT=POST_VARIANT_" + str(i))
                    print("RU_DAG_JSON_NATIVE_RETRYABLE=" + str(err.retryable))
                    if err.retryable:
                        raise
                    continue
                if "json" not in response.headers.get("content-type", "").lower():
                    raise ValueError("No first-party JSON content type")
                try:
                    payload = response.json()
                    identities = real_list_proof(payload)
                except (ValueError, TypeError):
                    print("RU_DAG_JSON_NATIVE_VARIANT_" + str(i) + "=NO_REAL_LIST_ITEMS")
                    continue
                print("RU_DAG_JSON_NATIVE_VARIANT=" + str(i))
                print("RU_DAG_JSON_NATIVE_REAL_LIST_ROWS=" + str(len(payload["items"])))
                print("RU_DAG_JSON_NATIVE_DISTINCT_LIST_IDENTITIES=" +
                      str(len(identities)))
                print("ORIGINAL_DETAIL_GET_VERIFIED=NO")
                print("WORKER_DB_TENANT_QUERY_VERIFIED=NO")
                return 0
    raise ValueError("No native public JSON listing entries")


def main():
    try:
        return asyncio.run(probe())
    except (ValueError, ConnectorTransportError, httpx.HTTPError,
            OSError, TimeoutError) as e:
        print("RU_DAG_JSON_NATIVE_DIRECT=BLOCKED_" + type(e).__name__)
        if isinstance(e, ConnectorTransportError):
            print("RU_DAG_RETRYABLE=" + str(e.retryable))
        return 2
    finally:
        print("PRODUCTION_CHANGED=NO")


if __name__ == "__main__":
    raise SystemExit(main())
