"""Official Chinese Inner Mongolia state procurement site anonymous accessibility.

No commercial mirrors, no guessed API, no login or CAPTCHA bypass.
Only same-host public HTML metadata/link shapes are reported.
"""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit,parse_qs,urljoin
import httpx

URLS={
  "cn_neimenggu_official_home":"https://www.ccgp-neimenggu.gov.cn/",
  "cn_neimenggu_official_gazette":"https://www.ccgp-neimenggu.gov.cn/maincms-web/articleNm?id=fa21287b-003a-4a69-94f0-20b80859724c&type=article",
}
class Links(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="a":
            href=dict(attrs).get("href")
            if href and len(self.links)<5000:
                self.links.append(href)
def main():
    proof={}
    with httpx.Client(timeout=20,follow_redirects=False,trust_env=False,
            headers={"Accept":"text/html","User-Agent":"VALYQON-OfficialTenderEvidence/1.0"}) as client:
        for key,url in URLS.items():
            out={"status":None,"bytes":0,"anchor_count":0,
                 "same_host_detail_links":0,"samples":[],"has_bidding_keywords":False}
            proof[key]=out
            try:
                with client.stream("GET",url) as response:
                    out["status"]=response.status_code
                    if response.status_code!=200:
                        continue
                    data=bytearray()
                    for block in response.iter_bytes():
                        data.extend(block)
                        if len(data)>1500000:
                            raise ValueError("response too large")
                out["bytes"]=len(data)
                text=data.decode("utf-8","replace")
                out["has_bidding_keywords"]=any(x in text for x in ("采购公告","招标公告","采购项目"))
                parser=Links();parser.feed(text)
                out["anchor_count"]=len(parser.links)
                for raw in parser.links:
                    uri=urlsplit(urljoin(url,raw))
                    if (uri.scheme!="https" or uri.hostname!="www.ccgp-neimenggu.gov.cn"
                          or uri.port not in (None,443)):
                        continue
                    if uri.path!="/maincms-web/articleNm":
                        continue
                    params=parse_qs(uri.query)
                    if not params.get("id") or params.get("type")!=["article"]:
                        continue
                    out["same_host_detail_links"]+=1
                    if len(out["samples"])<3:
                        out["samples"].append({"path":uri.path,"keys":sorted(params)})
                out["raw_article_route_mentions"]=len(re.findall(r"articleNm",text))
            except Exception as exc:
                out["error_type"]=type(exc).__name__
    print("CHINA_BORDER_MONGOLIA_OFFICIAL_PROCUREMENT_PROBE="+json.dumps(proof,sort_keys=True))
    print("PRODUCTION_CHANGED=NO")
    return 0
if __name__=="__main__":
    raise SystemExit(main())
