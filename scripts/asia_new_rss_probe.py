"""Independent anonymous official Asian RSS candidate check; research-only.

No source registration/production, no secrets, no item text. Never counts HTTP
200 without actual linked procurement entries, no automatic activation.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit, parse_qs
import httpx

FEEDS = {
    "sg_accommodation": "https://www.gebiz.gov.sg/rss/Accommodation-CREATE_BO_FEED.xml",
    "sg_construction": "https://www.gebiz.gov.sg/rss/Construction-CREATE_BO_FEED.xml",
    "sg_transportation": "https://www.gebiz.gov.sg/rss/Transportation-CREATE_BO_FEED.xml",
    "sg_it": "https://www.gebiz.gov.sg/rss/ITTelecommunication-CREATE_BO_FEED.xml",
    "sg_facilities": "https://www.gebiz.gov.sg/rss/FacilitiesManagement-CREATE_BO_FEED.xml",
    "sg_administration": "https://www.gebiz.gov.sg/rss/AdministrationTraining-CREATE_BO_FEED.xml",
    "sg_medical": "https://www.gebiz.gov.sg/rss/DentalMedicalLaboratory-CREATE_BO_FEED.xml",
    "sg_services": "https://www.gebiz.gov.sg/rss/Services-CREATE_BO_FEED.xml",
    "sg_equipment": "https://www.gebiz.gov.sg/rss/WorkshopEquipmentServices-CREATE_BO_FEED.xml",
    "hk_dsd_consultancy_eoi": "https://www.dsd.gov.hk/Menu/EN/RSS/Invitation_for_Expression_of_Interest_for_Consultancy_Agreements.xml",
}
def main():
    output = {}
    with httpx.Client(timeout=16, follow_redirects=False,
                      headers={"Accept": "application/rss+xml,application/xml,text/xml",
                               "User-Agent": "VALYQON-OfficialPublicFeedVerification/1.0"}) as client:
        for key, url in FEEDS.items():
            record = {"http_status": None, "bytes": 0, "items": 0,
                      "official_item_links": 0, "path_samples": []}
            output[key] = record
            try:
                with client.stream("GET", url) as response:
                    record["http_status"] = response.status_code
                    if response.status_code != 200:
                        continue
                    content = bytearray()
                    for block in response.iter_bytes():
                        content.extend(block)
                        if len(content) > 1048576:
                            raise ValueError("response-too-large")
                record["bytes"] = len(content)
                if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
                    raise ValueError("XML forbidden declaration")
                root = ET.fromstring(bytes(content))
                entries = root.findall("./channel/item") if root.tag == "rss" else (
                    root.findall("{http://purl.org/rss/1.0/}item")
                    if root.tag == "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF"
                    else [])
                record["items"] = len(entries)
                for item in entries:
                    link = item.findtext("link") or item.findtext("{http://purl.org/rss/1.0/}link")
                    title = item.findtext("title") or item.findtext("{http://purl.org/rss/1.0/}title")
                    if not title or not link:
                        continue
                    link_data = urlsplit(link)
                    if (link_data.scheme == "https"
                            and link_data.hostname == urlsplit(url).hostname
                            and link_data.username is None and link_data.password is None
                            and not link_data.fragment):
                        record["official_item_links"] += 1
                        if len(record["path_samples"]) < 2:
                            record["path_samples"].append({
                                "path": link_data.path[:160],
                                "params": sorted(parse_qs(link_data.query))[:8],
                            })
            except Exception as exc:
                record["error_type"] = type(exc).__name__
    print("ASIA_NEW_OFFICIAL_RSS_PROBE=" + json.dumps(output, sort_keys=True))
    print("PRODUCTION_CHANGED=NO")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
