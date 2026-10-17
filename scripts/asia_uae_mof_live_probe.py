"""Official UAE Ministry of Finance current-business-opportunity HTML structural probe.

Research-only: no accounts, redirects, credentials, productions DB or customers.
One bounded page and optional second official pagination with fixed parameters.
"""
from __future__ import annotations
import json
import html
import re
from urllib.parse import urlsplit, urljoin, parse_qs
import httpx

ROOT="https://mof.gov.ae/en/public-finance/government-procurement/current-business-opportunities/"
URLS=(ROOT,ROOT+"?mof-dpp-page=2")
def text(s):
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",s))).strip()

def main():
    records=[]
    with httpx.Client(timeout=22,follow_redirects=False,trust_env=False,
                      headers={"Accept":"text/html","User-Agent":"VALYQON-GovernmentTenderEvidence/1.0"}) as client:
        for url in URLS:
            row={"http_status":None,"bytes":0,"table_rows":0,"linked_official_rows":0,
                 "samples":[]}
            records.append(row)
            try:
                with client.stream("GET",url) as response:
                    row["http_status"]=response.status_code
                    if response.status_code!=200:
                        continue
                    data=bytearray()
                    for part in response.iter_bytes():
                        data.extend(part)
                        if len(data)>1500000:
                            raise ValueError("oversized")
                row["bytes"]=len(data)
                s=data.decode("utf-8","replace")
                row["contains_current_opportunities"]="Current Business Opportunities" in s
                row["contains_open_tenders"]="Open tenders" in s
                for table in re.findall(r"<table\b[^>]*>.*?</table>",s,re.I|re.S):
                    if "RFQ" not in text(table) and "Close Date" not in text(table):
                        continue
                    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>",table,re.I|re.S):
                        cells=re.findall(r"<td\b[^>]*>(.*?)</td>",tr,re.I|re.S)
                        if len(cells)<5:
                            continue
                        row["table_rows"]+=1
                        links=re.findall(r"""href=["']([^"']+)["']""",tr,re.I)
                        candidate=[]
                        for value in links:
                            d=urlsplit(urljoin(url,html.unescape(value)))
                            if d.scheme=="https" and d.hostname in {"mof.gov.ae","procurement.gov.ae"}:
                                candidate.append({
                                    "host":d.hostname,"path":d.path[:150],
                                    "query_keys":sorted(parse_qs(d.query))[:12]
                                })
                        if candidate:
                            row["linked_official_rows"]+=1
                        if len(row["samples"])<4:
                            row["samples"].append({"columns":len(cells),
                                "values":[text(c)[:90] for c in cells[:5]],
                                "links":candidate[:2]})
            except Exception as exc:
                row["error_type"]=type(exc).__name__
    print("UAE_FEDERAL_OFFICIAL_OPEN_TENDERS="+json.dumps(records,ensure_ascii=False,sort_keys=True))
    print("PRODUCTION_CHANGED=NO")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
