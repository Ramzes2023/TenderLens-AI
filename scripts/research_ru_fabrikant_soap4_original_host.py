"""Strict read-only check of the official Fabrikant soap4 original-detail host.

The official publisher publicly exposes /44/procedure/ea21/<19-digit EIS ID>
(e.g. an already published, independently linked historical record).
For a current Ingushetia notice ID supplied by a THIRD-PARTY index, the
same shape is only a HYPOTHESIS: validate the actual first-party HTML,
never treat the index as source authenticity or import its contents.

This does NOT discover a first-party current list; not source activation.
No authentication, proxy, TLS relaxation, redirects, cookies, copied
fixtures, subscriptions, production DB or notifications.
"""
from __future__ import annotations

import asyncio
import json
import re

from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client
from app.sources.lenobl_small_public import _Detail as Visible, _html as html_text

HOST="soap4.fabrikant.ru"
# First control URL appears as the linked original on the *official*
# Fabrikant requestOffer catalogue, including the original backurl.
CONTROL=(
    "https://soap4.fabrikant.ru/44/procedure/ea21/0372200119926000094"
    "?backurl=LzQ0L2NhdGFsb2cvcHJvY2VkdXJlL3JlcXVlc3RPZmZlcg%3D%3D"
)
# This candidate URL is constructed from the publisher's observed path
# grammar AND a third-party listed EIS ID: therefore NOT YET verified.
CURRENT_CANDIDATE="https://soap4.fabrikant.ru/44/procedure/ea21/0114500000826002518"

def classify(exc: BaseException) -> str:
    if isinstance(exc,ConnectorTransportError):
        category=getattr(exc,"reason","policy")
        return category if category in {
            "network","tls_certificate","http_status","http_transient",
            "policy","public_ip","response_size",
        } else "unclassified"
    if isinstance(exc,ValueError):
        return "original_contract"
    return "unclassified"


def public_original_markers(payload: bytes, *, current: bool) -> dict:
    if type(payload) is not bytes or not 0 < len(payload) <= 1_800_000:
        raise ValueError("Invalid original HTML response")
    parser=Visible()
    parser.feed(html_text(payload))
    parser.close()
    visible=" ".join(" ".join(parser.visible).split())
    if any(marker in visible.casefold() for marker in (
        "войдите в систему для просмотра",
        "необходимо авторизоваться",
        "необходима авторизация",
    )):
        raise ValueError("Login-only original is not independently verifiable")
    if current:
        return {
            "eis_id_visible":"0114500000826002518" in visible,
            "procurement_title_visible":"Поставка организационной техники".casefold() in visible.casefold(),
            "organizer_inn_visible":"0608058533" in visible,
            "independent_deadline_date_visible":"06.11.2026" in visible,
            "official_provenance":False,  # Only the genuine live GET can establish
        }
    return {
        "eis_id_visible":"0372200119926000094" in visible,
        "procurement_title_visible":"Поставка лекарственного препарата" in visible,
        "organizer_inn_visible":True, # No Ingushetia INN on historical control
        "independent_deadline_date_visible":"04.09.2026" in visible,
        "official_provenance":False,
    }


async def inspect() -> list[dict]:
    results=[]
    with bounded_fetch(FetchPolicy(frozenset({HOST}),2,max_bytes=1_800_000)):
        async with source_client(
            timeout=25,trust_env=False,follow_redirects=False,
            headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"},
        ) as client:
            for category,url in (("official_historical_control",CONTROL),
                                 ("new_ingushetia_hypothesis",CURRENT_CANDIDATE)):
                try:
                    response=await client.get(url)
                    response.raise_for_status()
                    if "html" not in response.headers.get("content-type","").lower():
                        raise ValueError("Official original not HTML")
                    proof=public_original_markers(
                        response.content,current=category=="new_ingushetia_hypothesis")
                    proof["official_provenance"]=True
                    passed=all(proof.values())
                    results.append({"source":category,"category":"verified_individual_original" if passed
                                    else "publisher_html_mismatch",
                                    "verified_marker_count":sum(proof.values()),
                                    "required_marker_count":len(proof)})
                except (ConnectorTransportError,ValueError) as exc:
                    results.append({"source":category,"category":classify(exc)})
                except Exception:
                    results.append({"source":category,"category":"unclassified"})
    return results


def main() -> int:
    results=asyncio.run(inspect())
    for outcome in results:
        print("FABRIKANT_SOAP4_ORIGINAL_PROBE="+json.dumps(outcome,sort_keys=True))
    print("SOURCE_LIST_DISCOVERY=NOT_PROVED")
    print("WORKER_SQL_SEARCH=NOT_PROVED")
    print("PUBLIC_SOURCES_ENABLED=NO")
    print("RELEASE_READY=NO")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
