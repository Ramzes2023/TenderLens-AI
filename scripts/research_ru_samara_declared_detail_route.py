"""Publisher-declared alternate Samara notice-detail route: read-only LIVE research.

Prior genuine Samara JSON listed 10 native records; direct individual detail
paths returned HTTP non-2xx. Never guess alternate endpoints. Only if the
official freshly fetched HTML *explicitly* advertises the fixed route AND
query key together may this diagnostic GET any alternate detail URL.

This is not an ingestion, Worker, tenant search or source deployment proof.
No authentication, cookies, redirects, TLS bypass, proxies, public-service
modification, invented identifiers, alerts, or production database writes.
"""
from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urlsplit

from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client
from app.sources.ru_samara_public_list import (
    HOST, GRID, JSON_URL, MAX_BYTES, public_token, public_settings,
    parse_public_list, canonical_id,
)
from app.sources.lenobl_small_public import _Detail as VisibleHtml, _html as html_text

# This literal is not permission to fetch it. A fresh official landing must
# advertise this exact route + key before *any* alternate detail request.
_PATH = "/smallpurchases/GzwSP/Notice"
_QUERY_KEY = "noticeLink"
_LIMIT = 2


def explicitly_announced(html: bytes) -> bool:
    if type(html) is not bytes or not 0 < len(html) <= MAX_BYTES or b"\x00" in html:
        return False
    # External scripts aren't authorization: the route and query must appear
    # in the *same* first-party publisher HTML document and within a narrow
    # adjacent code fragment. Ignore foreign <script src=...> content.
    visible = re.sub(rb"<script\b[^>]*\bsrc\s*=\s*[^>]+>.*?</script>", b"", html,
                     flags=re.I | re.S)
    pattern = rb"/smallpurchases/GzwSP/Notice(?:(?:\?noticeLink=)|.{0,180}\bnoticeLink\b)"
    return bool(re.search(pattern, visible, re.I | re.S))


def authorized_detail_url(native_link: str, *, published_html: bytes) -> str:
    if not explicitly_announced(published_html):
        raise ValueError("Publisher did not announce alternate public notice route")
    identity = canonical_id(native_link)  # independently validates HTTPS, host, ID
    if not identity.isascii() or not identity.isdecimal():
        raise ValueError("Invalid first-party numeric identity")
    return "https://" + HOST + _PATH + "?" + _QUERY_KEY + "=" + identity


async def inspect() -> dict:
    stage="GRID_GET"
    confirmed=0
    try:
        with bounded_fetch(FetchPolicy(frozenset({HOST}),2+_LIMIT,max_bytes=MAX_BYTES)):
            async with source_client(
                timeout=25,trust_env=False,follow_redirects=False,
                headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"},
            ) as client:
                landing=await client.get(GRID)
                landing.raise_for_status()
                if "html" not in landing.headers.get("content-type","").lower():
                    raise ValueError("Official public grid not HTML")
                stage="PUBLISHER_DECLARED_ALTERNATE_ROUTE"
                if not explicitly_announced(landing.content):
                    return {"stage":stage,"category":"not_declared_by_publisher",
                            "independent_details":0}
                stage="ANONYMOUS_GRID_TOKEN"
                token=public_token(landing.content)
                stage="NATIVE_JSON_POST"
                native=await client.post(JSON_URL,json={"settings":public_settings()},
                    headers={"Accept":"application/json, text/javascript",
                             "X-Requested-With":"XMLHttpRequest",
                             "Referer":GRID,
                             "RequestVerificationToken":token})
                native.raise_for_status()
                if "json" not in native.headers.get("content-type","").lower():
                    raise ValueError("No native JSON media type")
                response=native.json()
                stage="ORIGINAL_JSON_IDENTITY"
                notices=parse_public_list(response,limit=_LIMIT)
                if len(notices)!=_LIMIT or len(response.get("items",[]))<_LIMIT:
                    raise ValueError("Two different original list entries required")
                for notice,row in zip(notices,response["items"][:_LIMIT]):
                    url=authorized_detail_url(row.get("link"),published_html=landing.content)
                    stage="DECLARED_NOTICE_DETAIL_GET"
                    detail=await client.get(url,headers={"Accept":"text/html"})
                    detail.raise_for_status()
                    if "html" not in detail.headers.get("content-type","").lower():
                        raise ValueError("First-party original response not HTML")
                    stage="ORIGINAL_VISIBLE_FIELDS"
                    document=VisibleHtml()
                    document.feed(html_text(detail.content))
                    document.close()
                    visible=" ".join(" ".join(document.visible).split()).casefold()
                    if any(s in visible for s in (
                        "необходимо авторизоваться",
                        "войдите в систему для просмотра",
                        "необходима авторизация",
                    )):
                        raise ValueError("Not a public original detail")
                    if not all(
                        type(field) is str and field.casefold() in visible
                        for field in (notice.tender_number,notice.title,notice.customer)
                    ):
                        raise ValueError("First-party original mismatch")
                    confirmed+=1
                return {"stage":"ORIGINAL_VISIBLE_FIELDS",
                        "category":"native_firstparty_details_verified",
                        "independent_details":confirmed}
    except ConnectorTransportError as exc:
        known={"network","public_ip","tls_certificate","http_status",
               "http_transient","response_size","policy"}
        return {"stage":stage,"category":exc.reason if exc.reason in known
                else "unclassified","independent_details":confirmed}
    except ValueError:
        return {"stage":stage,"category":"original_contract",
                "independent_details":confirmed}
    except Exception:
        return {"stage":stage,"category":"unclassified",
                "independent_details":confirmed}


def main() -> int:
    result=asyncio.run(inspect())
    print("RU_SAMARA_DECLARED_DETAIL_ROUTE="+json.dumps(result,sort_keys=True))
    print("TWO_INDEPENDENT_OFFICIAL_ORIGINALS="+str(
        result["independent_details"]==2).upper())
    print("LEASED_WORKER_SQL_SEARCH=NOT_VERIFIED")
    print("PUBLIC_SOURCE_ENABLED=NO")
    print("RELEASE_READY=NO")
    return 0  # Research outcome only; failure never greenlights source.


if __name__=="__main__":
    raise SystemExit(main())
