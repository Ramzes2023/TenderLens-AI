"""Test two current Chechnya Fabrikant original detail URL hypotheses.

The current EIS notice IDs were located on independent secondary indexes,
NOT in first-party discovery. The only acceptable result is authentic
first-party soap4 HTML corroborating each ID, title, organizer INN and
published deadline. This is NOT a source-discovery or Worker release proof.
"""
from __future__ import annotations
import asyncio
import json

from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client
from app.sources.lenobl_small_public import _Detail as Visible, _html as html_text

HOST="soap4.fabrikant.ru"
ORIGINALS=(
    ("0194200000526005756", "Услуги по организации и проведению праздничных мероприятий"),
    ("0194200000526005775", "Поставка фармацевтических препаратов"),
)
def classify(exc):
    if isinstance(exc,ConnectorTransportError):
        v=getattr(exc,"reason","policy")
        return v if v in {"network","public_ip","tls_certificate","http_status",
                          "http_transient","response_size","policy"} else "unclassified"
    return "original_contract" if isinstance(exc,ValueError) else "unclassified"

def original_markers(payload,identity,title):
    if type(payload) is not bytes or not 0 < len(payload) <= 1_800_000:
        raise ValueError("Original HTML invalid")
    parser=Visible()
    parser.feed(html_text(payload))
    parser.close()
    content=" ".join(" ".join(parser.visible).split()).casefold()
    if any(x in content for x in ("необходима авторизация","необходимо авторизоваться",
                                 "войдите в систему для просмотра")):
        raise ValueError("Login page cannot prove original")
    return {"id": identity in content, "title":title.casefold() in content,
            "inn":"2016014690" in content, "deadline":"05.11.2026" in content}

async def check():
    out=[]
    with bounded_fetch(FetchPolicy(frozenset({HOST}),2,max_bytes=1_800_000)):
        async with source_client(
            timeout=25,trust_env=False,follow_redirects=False,
            headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"}
        ) as client:
            for identity,title in ORIGINALS:
                url=f"https://{HOST}/44/procedure/ea21/{identity}"
                try:
                    reply=await client.get(url)
                    reply.raise_for_status()
                    if "html" not in reply.headers.get("content-type","").lower():
                        raise ValueError("Publisher original did not return HTML")
                    flags=original_markers(reply.content,identity,title)
                    category="verified_individual_original" if all(flags.values()) else "original_mismatch"
                    out.append({"category":category,"verified_markers":sum(flags.values())})
                except Exception as exc:
                    out.append({"category":classify(exc)})
    return out

def main():
    for index,record in enumerate(asyncio.run(check()),1):
        print("CHECHNYA_SOAP4_FIRSTPARTY_DETAIL="+json.dumps(
            {"ordinal":index,**record},sort_keys=True))
    print("FIRSTPARTY_CURRENT_DISCOVERY=NOT_PROVED")
    print("WORKER_SQL_AND_SEARCH=NOT_PROVED")
    print("RELEASE_READY=NO")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
