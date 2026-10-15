"""Public-only diagnostic for the six staged Asian procurement feeds.

No credentials, production storage, dynamic target hosts, raw titles or response
bodies in logs. This is *observational* and is never a substitute for the strict
six-source database round-trip acceptance gate.
"""
from __future__ import annotations

import asyncio
import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

from app.sources.asia_public import (
    ASIA_RSS_FEEDS, JETRO_LISTS, _fetch, parse_asia_rss, parse_jetro_html,
)
from app.sources.eis_rss import SourceError

_RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF"
_ATOM = "{http://www.w3.org/2005/Atom}feed"
_ALLOWED_LISTS = {
    "jp_jetro_national": (
        JETRO_LISTS["jp_jetro_national"],
        JETRO_LISTS["jp_jetro_national"] + "?_page=1&deadline=1",
    ),
    "jp_jetro_local": (
        JETRO_LISTS["jp_jetro_local"],
        JETRO_LISTS["jp_jetro_local"] + "?_page=1&local_deadline=1",
    ),
}


async def _one(key: str, url: str) -> dict:
    item = {"source": key, "site": urlsplit(url).hostname, "stage": "NOT_VERIFIED",
            "records": 0, "response_bytes": 0, "xml_items": 0, "tender_links": 0}
    try:
        payload = await asyncio.wait_for(
            _fetch(url, 15, "application/xml" if key in ASIA_RSS_FEEDS else "text/html"),
            timeout=25,
        )
        item["response_bytes"] = len(payload)
        if key in ASIA_RSS_FEEDS:
            if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
                item["stage"] = "UNSAFE_XML"
                return item
            try:
                root = ET.fromstring(payload)
            except ET.ParseError:
                item["stage"] = "MALFORMED_XML"
                return item
            if root.tag == "rss":
                item["xml_items"] = len(root.findall("./channel/item"))
            elif root.tag == _ATOM:
                item["xml_items"] = len(root.findall("{http://www.w3.org/2005/Atom}entry"))
            elif root.tag == _RDF:
                item["xml_items"] = len(root.findall("{http://purl.org/rss/1.0/}item"))
            else:
                item["stage"] = "UNSUPPORTED_XML_ROOT"
                return item
            try:
                item["records"] = len(parse_asia_rss(payload, source=key, limit=5))
                item["stage"] = "PARSER_RETURNED_NOTICES"
            except SourceError:
                item["stage"] = "XML_VALID_BUT_NO_QUALIFIED_NOTICES"
        else:
            text = payload.decode("utf-8-sig", errors="replace")
            section = "national" if key.endswith("national") else "local"
            # Aggregate evidence only; never dump raw untrusted page content.
            needle = rf"/en/database/procurement/{section}/articles/"
            item["tender_links"] = len(re.findall(needle, text))
            item["table_rows"] = len(re.findall(r"<tr\b", text, re.IGNORECASE))
            try:
                item["records"] = len(parse_jetro_html(payload, source=key, limit=5))
                item["stage"] = "PARSER_RETURNED_NOTICES"
            except SourceError:
                item["stage"] = "HTML_VALID_BUT_NO_QUALIFIED_NOTICES"
    except asyncio.TimeoutError:
        item["stage"] = "TIMEOUT"
    except SourceError as error:
        message = str(error)
        match = re.fullmatch(r"Asian procurement upstream HTTP ([1-5][0-9][0-9])\.", message)
        if match:
            item["stage"] = "UPSTREAM_HTTP_" + match.group(1)
        elif message == "Asian procurement network/TLS unavailable.":
            item["stage"] = "NETWORK_OR_TLS_BLOCKED"
        else:
            item["stage"] = "UPSTREAM_OR_POLICY_BLOCKED"
    except Exception:
        item["stage"] = "UNEXPECTED_FAILURE"
    return item


async def main():
    results = []
    for key, url in (*ASIA_RSS_FEEDS.items(),):
        results.append(await _one(key, url))
    for key, urls in _ALLOWED_LISTS.items():
        for url in urls:
            value = await _one(key, url)
            value["variant"] = "explicit_active_query" if "?" in url else "base_listing"
            results.append(value)
    print("ASIA_SAFE_UPSTREAM_DIAGNOSTICS=" + json.dumps(results, sort_keys=True))
    print("ASIA_DIAGNOSTIC_IS_NOT_LIVE_ACCEPTANCE=YES")
    print("PRODUCTION_CHANGED=NO")


if __name__ == "__main__":
    asyncio.run(main())
