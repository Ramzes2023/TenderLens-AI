"""Independently check two actual original detail URLs from fresh Samara JSON.

Research-only. List records are *not* original detail proof. Never follow
redirects, authenticate, fabricate IDs, guess routes or weaken HTTPS. The
only permissible detail URLs must come from this request's own first-party
native JSON, pass the Samara canonical identity policy, and corroborate
notice number, buyer and title in a visible individual HTML body.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import nullcontext
from urllib.parse import urljoin

from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client
from app.sources.lenobl_small_public import _Detail as VisibleHtml, _html as html_text
from app.sources.ru_samara_public_list import (
    HOST, GRID, JSON_URL, MAX_BYTES, canonical_id, public_token,
    public_settings, parse_public_list,
)
from scripts.research_ru_samara_firstparty_native_transport import classify


async def inspect_details() -> dict:
    stage="GRID_GET"
    verified=0
    try:
        with bounded_fetch(FetchPolicy(frozenset({HOST}),4,max_bytes=MAX_BYTES)):
            async with source_client(
                timeout=25, trust_env=False, follow_redirects=False,
                headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"},
            ) as client:
                landing=await client.get(GRID)
                landing.raise_for_status()
                if "html" not in landing.headers.get("content-type","").lower():
                    raise ValueError("Official grid HTML expected")
                stage="GRID_TOKEN"
                token=public_token(landing.content)
                stage="NATIVE_JSON_POST"
                reply=await client.post(
                    JSON_URL,json={"settings":public_settings()},
                    headers={
                        "Accept":"application/json, text/javascript",
                        "X-Requested-With":"XMLHttpRequest",
                        "Referer":GRID,
                        "RequestVerificationToken":token,
                    },
                )
                reply.raise_for_status()
                if "json" not in reply.headers.get("content-type","").lower():
                    raise ValueError("Native JSON required")
                body=reply.json()
                stage="CANONICAL_NATIVE_ROWS"
                notices=parse_public_list(body,limit=2)
                if len(notices)!=2 or len(body["items"])<2:
                    raise ValueError("Two distinct native list rows required")
                for notice,row in zip(notices,body["items"][:2]):
                    raw=row.get("link")
                    if type(raw) is not str or canonical_id(raw)!=notice.external_id:
                        raise ValueError("Inconsistent native detail identity")
                    # Exact URL originates in the first-party public JSON.
                    detail_url=urljoin(GRID,raw)
                    stage="OFFICIAL_DETAIL_GET"
                    detail=await client.get(detail_url,headers={"Accept":"text/html"})
                    detail.raise_for_status()
                    if "html" not in detail.headers.get("content-type","").lower():
                        raise ValueError("Original detail HTML required")
                    stage="INDEPENDENT_DETAIL_FIELDS"
                    document=VisibleHtml()
                    document.feed(html_text(detail.content))
                    document.close()
                    visible=" ".join(" ".join(document.visible).split()).casefold()
                    if any(marker in visible for marker in (
                        "необходимо авторизоваться",
                        "войдите в систему для просмотра",
                        "необходима авторизация",
                    )):
                        raise ValueError("Public detail unavailable anonymously")
                    if not all(
                        isinstance(value,str) and value.casefold() in visible
                        for value in (
                            notice.tender_number, notice.title, notice.customer,
                        )
                    ):
                        raise ValueError("Original did not corroborate list title, ID and buyer")
                    verified+=1
                return {"stage":"INDEPENDENT_DETAIL_FIELDS",
                        "category":"independent_originals_verified",
                        "verified_original_details":verified}
    except (ConnectorTransportError,ValueError) as exc:
        return {"stage":stage,"category":classify(exc),
                "verified_original_details":verified}
    except Exception:
        return {"stage":stage,"category":"unclassified",
                "verified_original_details":verified}


def main() -> int:
    result=asyncio.run(inspect_details())
    print("RU_SAMARA_FIRSTPARTY_DETAIL_DIAGNOSTIC="+json.dumps(result,sort_keys=True))
    print("TWO_INDEPENDENT_DETAILS_CONFIRMED="+str(
        result["verified_original_details"]==2).upper())
    print("FENCED_WORKER_SQL_SEARCH=NOT_VERIFIED")
    print("PUBLIC_SOURCE_DEPLOYMENT=NO")
    print("RELEASE_READY=NO")
    return 0  # The diagnostic outcome must never be an approval to deploy.


if __name__=="__main__":
    raise SystemExit(main())
