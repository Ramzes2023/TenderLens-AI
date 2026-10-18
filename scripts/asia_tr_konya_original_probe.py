"""Anonymous first-party Konya tender source evidence only; NOT a production adapter.

GitHub-hosted probe makes at most 4 official HTTPS GETs (one listing, three
verified same-host detail pages) under the project's public-IP/TLS/DNS policy.
No log of user credentials, bids or private documents; fail closed on blocked
listing or missing original notice evidence.
"""
from __future__ import annotations

import asyncio
import html
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from app.sources.asia_public import _fetch, _safe_link
from app.sources.eis_rss import SourceError
from app.sources.http import FetchPolicy, bounded_fetch

INDEX = "https://www.konya.bel.tr/ihale"
HOSTS = frozenset({"www.konya.bel.tr"})
TURKEY = timezone(timedelta(hours=3))
HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
PATH = re.compile(r"^/ihale/[a-z0-9-]{12,180}$")
KIK = re.compile(r"İhale\s+Kayıt\s+Numarası\s*\(\s*İKN\s*\)\s*:?\s*(20\d\d/[1-9]\d{3,10})", re.I)
ICB = re.compile(r"ICB\s+Reference\s+No\s*:\s*(IDB-KON-G\d+)", re.I)
HEADER = re.compile(r"Son\s+Müracaat\s+Tarihi\s*:?\s*(\d\d\.\d\d\.20\d\d)\s*-\s*(\d\d:\d\d)", re.I)
ORIGINAL = re.compile(r"on or before\s+(\d\d:\d\d)\s*\(local time\)\s+on\s+(\d\d/\d\d/20\d\d)", re.I)
SALES = re.compile(r"(?:GAYRİMENKUL|SATIŞ\s+İHALE|MESKEN\s+SATIŞ|KİRA\s+İHALE)", re.I)

def visible(data: bytes) -> str:
    if not data or len(data) > 1024 * 1024:
        raise SourceError("Konya original HTML empty or too large.")
    raw = data.decode("utf-8", "replace")
    raw = re.sub(r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<!--.*?-->", " ", raw, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", raw))).strip()

def discover(data: bytes):
    if "İhaleler" not in visible(data):
        raise SourceError("Missing Konya municipal tender index.")
    found = []
    for href in HREF.findall(data.decode("utf-8", "replace")):
        try:
            link = _safe_link(html.unescape(href), HOSTS, base=INDEX)
        except SourceError:
            continue
        parts = urlsplit(link)
        if not parts.query and PATH.fullmatch(parts.path) and link not in found:
            found.append(link)
    if len(found) < 3:
        raise SourceError("Fewer than 3 official Konya municipal detail links.")
    return found

def classify(body: bytes, *, address: str):
    canonical = _safe_link(address, HOSTS)
    if not PATH.fullmatch(urlsplit(canonical).path) or urlsplit(canonical).query:
        raise SourceError("Unapproved Konya tender URL.")
    text = visible(body)
    if "İhale Sahibi" not in text or "Son Müracaat Tarihi" not in text:
        raise SourceError("Konya page lacks its own buyer and deadline.")
    match = HEADER.search(text)
    if not match:
        raise SourceError("Konya page lacks exact local application clock time.")
    date = datetime.strptime(" ".join(match.groups()), "%d.%m.%Y %H:%M").replace(tzinfo=TURKEY)
    if date <= datetime.now(TURKEY):
        return {"state": "expired", "path": urlsplit(canonical).path, "deadline": date.isoformat()}
    kik = KIK.search(text)
    icb = ICB.search(text)
    original = ORIGINAL.search(text)
    discrepancy = False
    if original:
        on_notice = datetime.strptime(original.group(2) + " " + original.group(1), "%d/%m/%Y %H:%M").replace(tzinfo=TURKEY)
        discrepancy = on_notice != date
    result = {"state": "candidate", "path": urlsplit(canonical).path,
              "deadline": date.isoformat(), "kik": kik.group(1) if kik else None,
              "icb": icb.group(1) if icb else None,
              "deadline_conflict": discrepancy, "property_sale": bool(SALES.search(text[:1200])),
              "ekap_syndicated": "EKAP" in text}
    if not (kik or icb):
        result["state"] = "missing_original_id"
    if discrepancy:
        result["state"] = "contradictory_original_deadline"
    if result["property_sale"]:
        result["state"] = "property_sale"
    return result

async def check():
    with bounded_fetch(FetchPolicy(HOSTS, max_requests=4, max_bytes=1024*1024)):
        index_html = await _fetch(INDEX, 20, "text/html")
        links = discover(index_html)
        markup = index_html.decode("utf-8", "replace")
        anchor_text = {}
        for match in re.finditer(r"<a\b[^>]*href\s*=\s*[\\"']([^\\"']+)[\\"'][^>]*>(.*?)</a\s*>",
                                 markup, re.I | re.S):
            try:
                candidate = _safe_link(html.unescape(match.group(1)), HOSTS, base=INDEX)
            except SourceError:
                continue
            if candidate in links:
                anchor_text[candidate] = re.sub(r"\s+", " ", visible(match.group(2).encode("utf-8")))[:260]
        # Require all detail links to be derived from the CURRENT first-party list.
        priority = sorted(links, key=lambda x: (
            0 if "procurement-of-goods" in x else
            1 if "standart-ctp" in x else 2 if "hocafakih" in x else 3,
            x))
        verified = []
        for link in priority[:3]:
            checked = classify(await _fetch(link, 20, "text/html"), address=link)
            verified.append(checked)
    accepted = sum(x["state"] == "candidate" for x in verified)
    failures = sum(x["state"] == "contradictory_original_deadline" for x in verified)
    print("KONYA_REAL_FIRST_PARTY_RESEARCH=" + json.dumps({
        "original_index_details": len(links), "probed": verified,
        "index_anchor_samples": [anchor_text.get(link, "") for link in priority[:3]],
        "potential_current_notices": accepted, "blocked_conflicting_deadlines": failures,
        "production_connector_registered": False, "production_changed": False
    }, ensure_ascii=False, sort_keys=True))
    # The research validates public originals, not a working adapter. At least
    # two unexpired, numbered official details are required to pass this gate.
    return 0 if len(verified) == 3 and accepted >= 2 else 3

if __name__ == "__main__":
    raise SystemExit(asyncio.run(check()))
