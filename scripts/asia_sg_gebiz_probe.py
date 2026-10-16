"""Strict no-credential public GeBIZ RSS availability and structure probe.

The probe is research only. It prints no raw RSS descriptions, secrets or
customer data. It does not enqueue, persist, activate or claim source coverage.
"""
import json
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
import httpx

FEEDS = (
    "https://www.gebiz.gov.sg/rss/Professional_Services-CREATE_BO_FEED.xml",
    "https://www.gebiz.gov.sg/rss/OthersMiscellaneous-CREATE_BO_FEED.xml",
)

def main():
    summaries = {}
    for url in FEEDS:
        label = urlsplit(url).path.rsplit("/", 1)[-1].split("-")[0]
        out = {"status": "NOT_CHECKED", "size": 0, "items": 0, "links": []}
        summaries[label] = out
        try:
            with httpx.Client(timeout=25, follow_redirects=False,
                              headers={"Accept": "application/rss+xml,application/xml,text/xml",
                                       "User-Agent": "VALYQON-OfficialRSSValidation/1.0"}) as client:
                with client.stream("GET", url) as response:
                    out["status"] = response.status_code
                    if response.status_code != 200:
                        continue
                    data = bytearray()
                    for part in response.iter_bytes():
                        data.extend(part)
                        if len(data) > 1048576:
                            raise ValueError("oversized")
            out["size"] = len(data)
            if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
                raise ValueError("xml-declaration")
            root = ET.fromstring(bytes(data))
            out["root"] = root.tag[:140]
            entries = root.findall("./channel/item")
            if not entries:
                entries = list(root.findall("{http://purl.org/rss/1.0/}item"))
            out["items"] = len(entries)
            for entry in entries[:5]:
                raw = entry.findtext("link") or entry.findtext("{http://purl.org/rss/1.0/}link") or ""
                link = urlsplit(raw)
                title = entry.findtext("title") or entry.findtext("{http://purl.org/rss/1.0/}title")
                out["links"].append({
                    "scheme": link.scheme, "host": link.hostname,
                    "path": link.path[:180], "query_keys": list(dict.fromkeys(
                        key.partition("=")[0] for key in link.query.split("&") if key))[:10],
                    "title_present": bool(title),
                })
        except Exception as exc:
            out["error_class"] = type(exc).__name__
    print("GEBIZ_PUBLIC_RSS_STRUCTURE=" + json.dumps(summaries, sort_keys=True))
    print("PRODUCTION_CHANGED=NO")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
