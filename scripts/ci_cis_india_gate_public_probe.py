"""Read-only diagnosis of unrelated mandatory India gate, not a source activation.

Sanitized counts/reasons from ONE official HTTPS page. Does not log HTML, URLs
with session tokens, external IDs, details, response headers, or credentials.
"""
import asyncio
import json
import re

from app.sources.http import FetchPolicy, bounded_fetch, source_client
from app.sources.india_epublish import LIST_URL, HOME, _TR, _TD, _text, _verified_portal_detail, parse_epublish_latest

async def run():
    report={"source":"in_epublish","production_changed":False}
    try:
        with bounded_fetch(FetchPolicy(frozenset({"eprocure.gov.in"}),1,max_bytes=1024*1024)):
            async with source_client(timeout=25,trust_env=False,follow_redirects=False) as client:
                response=await client.get(LIST_URL)
        report["status"]=response.status_code
        report["html_type"]="html" in response.headers.get("content-type","").lower()
        if response.status_code!=200 or not report["html_type"]:
            print(json.dumps(report,sort_keys=True));return 1
        body=response.content
        decoded=body.decode("utf-8","replace")
        i=decoded.casefold().find("latest tenders")
        j=decoded.casefold().find("latest corrigendum",i+1)
        report.update({"html_bytes":len(body),"section_start":i>=0,"corrigendum_end":j>i,
                       "has_tender_title":"Tender Title" in decoded[max(i,0):max(j,0)] if j>i>=0 else False})
        if j>i>=0:
            rows=_TR.findall(decoded[i:j])
            report["rows"]=len(rows)
            report["rows_with_four_cells"]=sum(len(_TD.findall(r))==4 for r in rows)
            report["first_party_direct_links"]=sum(_verified_portal_detail(r) for r in rows)
            report["rows_with_close_open_dates"]=sum(bool(re.search(r"\d{2}-[A-Z][a-z]{2}-20\d{2}",_text(r))) for r in rows)
        try:
            notices=parse_epublish_latest(body,limit=10)
            report["parsed_real_opportunities"]=len(notices)
        except Exception as exc:
            report["parser_error_type"]=type(exc).__name__
            report["parser_safe_code"]="no_active_or_changed_schema"
        print(json.dumps(report,sort_keys=True))
        return 0 if report.get("parsed_real_opportunities",0)>0 else 1
    except Exception as exc:
        print(json.dumps({**report,"transport_error_type":type(exc).__name__},sort_keys=True))
        return 1

if __name__=="__main__":
    raise SystemExit(asyncio.run(run()))
