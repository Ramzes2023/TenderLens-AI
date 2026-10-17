"""Live government Ankara municipality open tender page/detail structure.

A strict read-only probe that prints bounded structural HTML evidence, never
credentials or non-government notice details. No connector activation.
"""
import html
import json
import re
from urllib.parse import urlsplit,urljoin
import httpx

URLS=("https://www.ankara.bel.tr/ihaleler","https://www.ankara.bel.tr/ihaleler/detay/4149")
def clean(s):
 return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",s))).strip()
def main():
 result={}
 with httpx.Client(timeout=18,follow_redirects=False,trust_env=False,
                   headers={"Accept":"text/html","User-Agent":"VALYQON-OfficialTenderEvidence/1.0"}) as client:
  for url in URLS:
   info={"status":None,"bytes":0,"same_origin_details":0,"detail_examples":[],"block_shapes":[]}
   result[urlsplit(url).path]=info
   try:
    with client.stream("GET",url) as r:
     info["status"]=r.status_code
     if r.status_code!=200:continue
     data=bytearray()
     for chunk in r.iter_bytes():
      data.extend(chunk)
      if len(data)>1100000:raise ValueError("oversized")
    info["bytes"]=len(data)
    h=data.decode("utf-8","replace")
    info["page_has_tenders"]="İhaleler" in h
    for m in re.finditer(r'''href=["']([^"']*/ihaleler/detay/[0-9]+)["']''',h,re.I):
     parsed=urlsplit(urljoin(url,html.unescape(m.group(1))))
     if parsed.scheme=="https" and parsed.hostname=="www.ankara.bel.tr" and not parsed.query:
      info["same_origin_details"]+=1
      if len(info["detail_examples"])<5:
       info["detail_examples"].append(parsed.path)
       # Show only element tag names surrounding actual link for robust parser choice.
       prefix=h[max(0,m.start()-1200):m.start()]
       info["block_shapes"].append({
        "tags":[x.lower() for x in re.findall(r"<\s*([a-z][a-z0-9-]*)\b",prefix,re.I)][-14:],
        "text_tail":clean(prefix)[-230:],
       })
    if "/detay/" in url:
     for token in ("İhale Konusu","İhale Birimi","KİK Kayıt No","İhale Tarihi/Saati"):
      match=re.search(re.escape(token),h)
      info[token]={"present":bool(match),
        "followed_by":clean(h[match.end():match.end()+600])[:200] if match else ""}
   except Exception as ex:
    info["error_type"]=type(ex).__name__
 print("TURKEY_ANKARA_REAL_HTML_STRUCTURE="+json.dumps(result,ensure_ascii=False,sort_keys=True))
 print("PRODUCTION_CHANGED=NO")
 return 0
if __name__=="__main__":
 raise SystemExit(main())
