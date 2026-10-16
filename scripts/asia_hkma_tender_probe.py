"""Official Hong Kong Monetary Authority tender API anonymous research gate.

Outputs response metadata, NOT raw notices. Unavailable or award-only data
never counts as a successful tender integration.
"""
import json
import httpx
from urllib.parse import urlsplit, parse_qs

URL = "https://api.hkma.gov.hk/public/tender-invitations"
def main():
    results={}
    with httpx.Client(timeout=22, follow_redirects=False,
                      headers={"Accept":"application/json"}) as client:
        for segment in ("tender", "notice"):
            info={"http_status":None,"json_valid":False,"result_keys":[],"count":0,"sample":[]}
            results[segment]=info
            try:
                with client.stream("GET",URL,params={"lang":"en","segment":segment,"pagesize":"30"}) as resp:
                    info["http_status"]=resp.status_code
                    if resp.status_code!=200:
                        continue
                    body=bytearray()
                    for chunk in resp.iter_bytes():
                        body.extend(chunk)
                        if len(body)>1024*1024:
                            raise ValueError("size")
                data=json.loads(body)
                if not isinstance(data,dict):
                    continue
                info["json_valid"]=True
                result=data.get("result")
                if not isinstance(result,dict):
                    info["top_keys"]=list(data)[:20]
                    continue
                info["result_keys"]=list(result)[:20]
                records=result.get("records")
                if isinstance(records,list):
                    info["count"]=len(records)
                    for x in records[:3]:
                        if not isinstance(x,dict):
                            continue
                        raw=x.get("link","") or ""
                        url=urlsplit(raw)
                        info["sample"].append({
                            "keys":sorted(x)[:18],"title_present":bool(x.get("title")),
                            "host":url.hostname,"scheme":url.scheme,
                            "path":url.path[:160],"query_keys":sorted(parse_qs(url.query))[:12],
                            "date_sample":str(x.get("date",""))[:30],
                            "date_present":bool(x.get("date")),
                        })
            except Exception as exc:
                info["error_type"]=type(exc).__name__
    print("HKMA_OFFICIAL_TENDER_PROBE="+json.dumps(results,sort_keys=True))
    print("PRODUCTION_CHANGED=NO")
    return 0
if __name__=="__main__":
    raise SystemExit(main())
