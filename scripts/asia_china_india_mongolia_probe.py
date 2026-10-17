"""Anonymous one-GET verification of official China and nearby Asia tender listings.

Research only: bounded 0.9 MiB per response, no POST/login, no bypass,
no real tender data printed, never marks status 200 as actual source coverage.
"""
from __future__ import annotations
import json
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin
import httpx

CANDIDATES={
    "cn_ccgp_local_open":"https://www.ccgp.gov.cn/cggg/dfgg/gkzb/index.htm",
    "cn_ccgp_central_open":"https://www.ccgp.gov.cn/cggg/zygg/gkzb/index.htm",
    "cn_ccgp_local_inquiry":"https://www.ccgp.gov.cn/cggg/dfgg/xjgg/index.htm",
    "cn_ccgp_central_negotiation":"https://www.ccgp.gov.cn/cggg/zygg/jzxcs/index.htm",
    "in_epublish":"https://eprocure.gov.in/epublish/app",
    "mn_public_tenders":"https://www.tender.gov.mn/mn/invitation",
    "tr_ekap_search":"https://ekap.kik.gov.tr/EKAP/Ortak/ihaleArama/index.html",
}
class Links(HTMLParser):
    def __init__(self):
        super().__init__();self.anchors=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="a":
            d=dict(attrs)
            if d.get("href") and len(self.anchors)<1000:
                self.anchors.append(d["href"])

def main():
    out={}
    with httpx.Client(timeout=18,follow_redirects=False,trust_env=False,
            headers={"User-Agent":"VALYQON-PublicProcurementVerification/1.0",
                     "Accept":"text/html,application/xhtml+xml"}) as client:
        for key,url in CANDIDATES.items():
            item={"status":None,"bytes":0,"links":0,"detail_candidate_count":0,
                  "sample_paths":[]}
            out[key]=item
            try:
                with client.stream("GET",url) as response:
                    item["status"]=response.status_code
                    item["content_type"]=response.headers.get("Content-Type","")[:100]
                    if response.status_code!=200:
                        continue
                    data=bytearray()
                    for block in response.iter_bytes():
                        data.extend(block)
                        if len(data)>900000:
                            raise ValueError("response exceeds bound")
                item["bytes"]=len(data)
                parser=Links();parser.feed(data.decode("utf-8","replace"))
                item["links"]=len(parser.anchors)
                for link in parser.anchors:
                    safe=urlsplit(urljoin(url,link))
                    if (safe.scheme!="https" or safe.hostname!=urlsplit(url).hostname
                            or safe.port not in (None,443) or safe.fragment):
                        continue
                    path=safe.path
                    is_notice=(
                        (key.startswith("cn_") and "/cggg/" in path and
                         "/t20" in path and path.endswith(".htm")) or
                        (key=="in_epublish" and ("DirectLink" in link or "%24DirectLink" in link)) or
                        (key=="mn_public_tenders" and ("/invitation/" in path or "/tender/" in path))
                    )
                    if is_notice:
                        item["detail_candidate_count"]+=1
                        if len(item["sample_paths"])<4:
                            item["sample_paths"].append(path[:150])
            except Exception as exc:
                item["error_type"]=type(exc).__name__
    print("ASIA_RUSSIA_FRIENDLY_OFFICIAL_DISCOVERY="+json.dumps(out,sort_keys=True))
    print("PRODUCTION_CHANGED=NO")
    return 0
if __name__=="__main__":
    raise SystemExit(main())
