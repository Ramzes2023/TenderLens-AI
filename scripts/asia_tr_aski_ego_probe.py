"""Government Ankara ASKİ and EGO public bid list/detail verification.

Only fixed official GETs; no login, submissions, captcha, page crawling or
production data. Print bounded known-public field shapes to guide adapters.
"""
import html,json,re
from urllib.parse import urlsplit,urljoin,parse_qs
import httpx

URLS={
 "aski_list":"https://www.aski.gov.tr/tr/ihale.aspx",
 "aski_example":"https://www.aski.gov.tr/tr/IhaleDetay.aspx?ID=3746",
 "ego_list":"https://www.ego.gov.tr/ihaleler",
 "ego_example":"https://www.ego.gov.tr/tr/ihale/detay/11894/metro-isletme-sube-mudurlugu-crrc-trenleri-icin-bo?tip=0",
}
def norm(x):
 return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",x))).strip()
def main():
 out={}
 with httpx.Client(timeout=17,follow_redirects=False,trust_env=False,
   headers={"Accept":"text/html,application/xhtml+xml","User-Agent":"VALYQON-OfficialTendersResearch/1.0"}) as c:
  for key,url in URLS.items():
   record={"status":None,"bytes":0,"verified_detail_links":0,"examples":[]}
   out[key]=record
   try:
    with c.stream("GET",url) as response:
     record["status"]=response.status_code
     if response.status_code!=200:continue
     b=bytearray()
     for chunk in response.iter_bytes():
      b.extend(chunk)
      if len(b)>1000000:raise ValueError("response too large")
    record["bytes"]=len(b)
    raw=b.decode("utf-8","replace")
    for link in re.findall(r"""href=["']([^"']+)["']""",raw,re.I):
     parsed=urlsplit(urljoin(url,html.unescape(link)))
     if parsed.scheme!="https" or parsed.hostname!=urlsplit(url).hostname:
      continue
     a=bool(key.startswith("aski") and re.fullmatch(r"/tr/IhaleDetay\.aspx",parsed.path,re.I)
            and len(parse_qs(parsed.query).get("ID",[]))==1)
     e=bool(key.startswith("ego") and re.fullmatch(r"/tr/ihale/detay/[0-9]+/[^/]+",parsed.path,re.I))
     if a or e:
      record["verified_detail_links"]+=1
      if len(record["examples"])<4:
       record["examples"].append({"path":parsed.path,"query_keys":sorted(parse_qs(parsed.query))})
    record["markers"]={s:bool(re.search(s,raw,re.I)) for s in
     ("Kik Kayıt Numarası","KİK KAYIT NO","İhale Tarihi","İHALE TARİHİ","İhale Adı","İHALE ADI")}
    if key.endswith("example"):
     text=norm(raw)
     for s in ("İhale Kayıt Numarası (İKN)","İHALE ADI","İhale konusu","İHALE BİRİMİ","KİK KAYIT NO","İhale Tarihi"):
      match=re.search(re.escape(s),text,re.I)
      if match:record["field_samples_"+str(len(record))]=text[match.start():match.start()+130]
   except Exception as exc:record["error_type"]=type(exc).__name__
 print("TURKEY_ASKI_EGO_GOVERNMENT_NOTICE_PROOF="+json.dumps(out,ensure_ascii=False,sort_keys=True))
 print("PRODUCTION_CHANGED=NO")
 return 0
if __name__=="__main__":
 raise SystemExit(main())
