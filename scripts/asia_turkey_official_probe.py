"""Read-only official Türkiye procurement HTML validation from hosted runner.

No login, auth, CAPTCHA, crawled detail pages, retry storms or credentials.
Only safe sampled title/date/link shapes from latest anonymous GETs.
"""
from __future__ import annotations
import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin, parse_qs
import httpx

URLS={
 "tr_botas_oct":"https://www.botas.gov.tr/Kategori/ihale-ilanlari/3?ay=10&yil=2026",
 "tr_botas_sep":"https://www.botas.gov.tr/Kategori/ihale-ilanlari/3?ay=9&yil=2026",
 "tr_tcdd_tasimacilik":"https://www.tcddtasimacilik.gov.tr/tr/ihale_lanlari",
 "tr_tcdd":"https://www.tcdd.gov.tr/ihaleler/",
 "tr_ilan":"https://www.ilan.gov.tr/ilan/tum-ilanlar/ihale?currentPage=0",
 "tr_dmo":"https://www.dmo.gov.tr/Ihale",
 "tr_kik":"https://ekap.kik.gov.tr/EKAP/Ortak/ihaleArama/index.html",
 "tr_kgm":"https://www.kgm.gov.tr/Sayfalar/KGM/SiteTr/Root/rss.aspx",
}
class Parser(HTMLParser):
 def __init__(self):
  super().__init__();self.links=[]
 def handle_starttag(self,tag,attrs):
  if tag.lower()=="a":
   x=dict(attrs)
   if x.get("href") and len(self.links)<1500:
    self.links.append((x["href"],""))
 def handle_data(self,data):
  if self.links:
   href,title=self.links[-1]
   if len(title)<100:self.links[-1]=(href,(title+" "+data).strip()[:160])
def main():
 out={}
 with httpx.Client(timeout=18,follow_redirects=False,trust_env=False,
     headers={"User-Agent":"VALYQON-AI/1.0 (official tender research)",
              "Accept":"text/html,application/xhtml+xml"}) as cli:
  for k,url in URLS.items():
   x={"status":None,"size":0,"anchors":0,"official_tender_links":0,"examples":[]}
   out[k]=x
   try:
    with cli.stream("GET",url) as response:
     x["status"]=response.status_code
     x["content_type"]=response.headers.get("content-type","")[:70]
     if response.status_code!=200:continue
     data=bytearray()
     for piece in response.iter_bytes():
      data.extend(piece)
      if len(data)>1400000:raise ValueError("oversized")
    x["size"]=len(data)
    h=data.decode("utf-8","replace")
    p=Parser();p.feed(h);x["anchors"]=len(p.links)
    for href,title in p.links:
     link=urlsplit(urljoin(url,html.unescape(href)))
     if link.scheme!="https" or link.hostname!=urlsplit(url).hostname or link.port not in (None,443):
      continue
     good=(k.startswith("tr_botas") and re.fullmatch(r"/Icerik/[a-z0-9-]+/[0-9]{2,8}",link.path,re.I)) or (
       k=="tr_tcdd_tasimacilik" and ("ihale" in link.path.lower() and link.path!=urlsplit(url).path)) or (
       k=="tr_ilan" and re.fullmatch(r"/ilan/[0-9]{5,12}/.+",link.path)) or (
       k=="tr_dmo" and re.fullmatch(r"/Ihale/Detay/[0-9]{2,12}",link.path,re.I))
     if good:
      x["official_tender_links"]+=1
      if len(x["examples"])<5:
       x["examples"].append({"path":link.path[:150],"title":re.sub(r"\s+"," ",title)[:100],
                            "query_keys":sorted(parse_qs(link.query))[:8]})
    x["markers"]={term:h.lower().count(term) for term in
      ("ihale ilanları","ihale duyurları","2026","captcha","ilan metni")}
   except Exception as ex:x["error_type"]=type(ex).__name__
 print("TURKEY_OFFICIAL_ANON_TENDER_PROBE="+json.dumps(out,ensure_ascii=False,sort_keys=True))
 print("PRODUCTION_CHANGED=NO")
 return 0
if __name__=="__main__":
 raise SystemExit(main())
