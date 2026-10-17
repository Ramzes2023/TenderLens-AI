"""Strict read-only discovery of two published Russian procurement inventories.

Research-only. No production settings, cookies, authentication, redirects, proxies,
custom trust or fake notice success. Real HTTPS and bounded bytes via source_client.
"""
from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlsplit
from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client
from app.sources.gpb_etp_public import parse_gpb_verified_detail

GPB_HOST = "etpgpb.ru"
GPB_URL = "https://etpgpb.ru/procedures.rss"
VOLOGDA_HOST = "szvo.gov35.ru"
VOLOGDA_URL = "https://szvo.gov35.ru/web/gz/em_reestr"
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
GPB_DETAIL = re.compile(r"/procedures/etp/([0-9]{5,10})-[a-z0-9-]+/")
MAX_BYTES = 1_800_000


class LinkReader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hrefs = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if type(href) is str:
                self.hrefs.append(href)


async def gpb():
    with bounded_fetch(FetchPolicy(frozenset({GPB_HOST}), 3, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=26, follow_redirects=False, trust_env=False,
            headers={"Accept": "application/rss+xml, application/xml, text/xml", "User-Agent": "Mozilla/5.0"},
        ) as client:
            r = await client.get(GPB_URL)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            items = root.findall("./channel/item")
            print("RU_GPB_RSS_ENTRIES=" + str(len(items)))
            print("RU_GPB_RSS_ROOT=" + root.tag)
            found = []
            for item in items:
                link = (item.findtext("link") or "").strip()
                uri = urlsplit(link)
                m = GPB_DETAIL.fullmatch(uri.path)
                if uri.scheme == "https" and uri.netloc == GPB_HOST and m and not uri.query and not uri.fragment:
                    obj = (m.group(1), link)
                    if obj not in found:
                        found.append(obj)
            print("RU_GPB_RSS_CANONICAL_DETAIL_LINKS=" + str(len(found)))
            ok = 0
            for identity, url in found[:2]:
                page = await client.get(url)
                page.raise_for_status()
                notice = parse_gpb_verified_detail(page.content, identity, url)
                ok += notice.external_id == identity and notice.source == "gpb_etp_public"
            print("RU_GPB_RSS_DETAIL_VERIFIED=" + str(ok))
            return len(found) >= 2 and ok == 2


async def vologda():
    with bounded_fetch(FetchPolicy(frozenset({VOLOGDA_HOST}), 3, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=26, follow_redirects=False, trust_env=False,
            headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
        ) as client:
            r = await client.get(VOLOGDA_URL)
            r.raise_for_status()
            if "html" not in r.headers.get("content-type", "").lower():
                print("RU_VOLOGDA_LIST_HTML=NO")
                return False
            doc = LinkReader()
            doc.feed(r.content.decode("utf-8-sig", "replace"))
            found = []
            for raw in doc.hrefs:
                p = urlsplit(raw)
                # Do not follow a discovered href. Only accept IDs in links on exact
                # fixed official path, and construct a new known-safe URL ourselves.
                query = parse_qs(p.query, keep_blank_values=True)
                uid = query.get("_EM_WAR_EMportlet_docId", [""])[0]
                if (p.scheme in ("", "https") and (not p.netloc or p.netloc == VOLOGDA_HOST)
                        and (p.path in ("", "/web/gz/em_reestr") or p.path.startswith("/web/gz/em_reestr;"))
                        and UUID.fullmatch(uid) and uid not in found):
                    found.append(uid)
            print("RU_VOLOGDA_LIST_ANCHORS=" + str(len(doc.hrefs)))
            print("RU_VOLOGDA_OFFICIAL_DETAIL_UUID_LINKS=" + str(len(found)))
            ok = 0
            for uid in found[:2]:
                query = urlencode({
                    "p_p_id": "EM_WAR_EMportlet",
                    "p_p_lifecycle": "0",
                    "p_p_state": "pop_up",
                    "p_p_mode": "view",
                    "_EM_WAR_EMportlet_docId": uid,
                    "_EM_WAR_EMportlet_jspPage": "/JSP/EM/view.jsp",
                })
                target = VOLOGDA_URL + "?" + query
                page = await client.get(target)
                page.raise_for_status()
                txt = page.content.decode("utf-8-sig", "replace")
                if "Информация о процедуре закупки" in txt and "Предмет контракта" in txt:
                    ok += 1
            print("RU_VOLOGDA_DETAIL_HTML_VERIFIED=" + str(ok))
            return len(found) >= 2 and ok == 2


async def main(which):
    try:
        valid = await (gpb() if which == "gpb" else vologda())
        print("RU_OFFICIAL_DISCOVERY=" + ("PASS" if valid else "BLOCKED_INCOMPLETE"))
        print("PRODUCTION_CHANGED=NO")
        return 0 if valid else 2
    except (ConnectorTransportError, Exception) as error:
        print("RU_OFFICIAL_DISCOVERY_BLOCKED=" + type(error).__name__)
        if isinstance(error, ConnectorTransportError):
            print("RU_OFFICIAL_DISCOVERY_RETRYABLE=" + str(error.retryable))
        print("PRODUCTION_CHANGED=NO")
        return 2


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2 or sys.argv[1] not in ("gpb", "vologda"):
        raise SystemExit("Usage: python -m scripts.research_ru_official_rss gpb|vologda")
    raise SystemExit(asyncio.run(main(sys.argv[1])))
