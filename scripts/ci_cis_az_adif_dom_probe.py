"""Read-only bounded real HTML structural audit of independent Azerbaijani small quotations.

No source activation, no SQLite, no synthetic fixtures. Human approval and a
real live list -> normalized notices -> DB search acceptance are required later.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from html.parser import HTMLParser
import json
import re

from app.sources.http import FetchPolicy, bounded_fetch, source_client

URL = "https://adif.gov.az/az/sale/"
HOST = "adif.gov.az"
MAX_BYTES = 1_800_000

class Audit(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.nodes = []
        self.hidden = 0
        self.tags = Counter()

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag)
        self.tags[tag] += 1
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "template"} and self.hidden:
            self.hidden -= 1
        if tag in self.stack:
            i = len(self.stack) - 1 - self.stack[::-1].index(tag)
            self.stack = self.stack[:i]

    def handle_data(self, value):
        if self.hidden:
            return
        v = " ".join(value.split())
        if len(v) > 5:
            self.nodes.append({"tag": self.stack[-1] if self.stack else "",
                               "parents": "/".join(self.stack[-4:]),
                               "text": v})

class _Sections(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.current = None
        self.records = []
        self.in_hidden = 0
        self.tag = ""
    def handle_starttag(self, tag, attrs):
        if tag in ("script","style"):
            self.in_hidden += 1
        if tag == "article":
            if self.current is None:
                self.current = {"sections":0,"heads":[],"texts":[],"links":[]}
            self.depth += 1
        if self.current is not None:
            if tag in ("h3", "p", "h4", "strong", "b"):
                self.tag = tag
            if tag == "a":
                href = dict(attrs).get("href", "")
                if href and len(self.current["links"]) < 12:
                    self.current["links"].append(href[:160])
    def handle_endtag(self, tag):
        if tag == "article" and self.current is not None:
            self.depth -= 1
            if self.depth == 0:
                self.records.append(self.current)
                self.current = None
        if tag == self.tag:
            self.tag = ""
        if tag in ("script","style") and self.in_hidden:
            self.in_hidden -= 1
    def handle_data(self, data):
        if self.current is None or self.in_hidden:
            return
        value = " ".join(data.split())
        if not value:
            return
        if self.tag in ("h3", "h4", "strong", "b"):
            self.current["heads"].append(value[:350])
        if self.tag == "p" and len(self.current["texts"]) < 35:
            self.current["texts"].append(value[:190])


async def run():
    try:
        with bounded_fetch(FetchPolicy(frozenset({HOST}), 1, max_bytes=MAX_BYTES)):
            async with source_client(timeout=18.0, follow_redirects=False, trust_env=False) as client:
                response = await client.get(URL)
        if response.status_code != 200 or "html" not in response.headers.get("content-type", "").lower():
            raise RuntimeError("No real HTML")
        parser = Audit()
        parser.feed(response.text)
        sections = _Sections()
        sections.feed(response.text)
        sampled = [node for node in parser.nodes if any(s in node["text"].casefold()
                   for s in ("kotirovka", "satınalma", "təkliflər", "yerləşdirilmə tarixi"))]
        evidence = {
            "passed": True, "upstream": HOST, "http_status": response.status_code,
            "html_bytes": len(response.content),
            "candidate_text_nodes": len(sampled),
            "structural_tag_counts": {k: parser.tags[k] for k in ("div", "h1", "h2", "h3", "h4", "p", "article", "section", "a")},
            "sample_tags": [{"tag": n["tag"], "parents": n["parents"], "text_prefix": n["text"][:145]}
                            for n in sampled[:15]],
            "recent_oct_2026": sum(bool(re.search(r"02[.]10[.]2026", n["text"])) for n in parser.nodes),
            "article_count": len(sections.records),
            "articles_first6": [
                {"heads": v["heads"][:3], "texts": v["texts"][:15],
                 "links": v["links"][:5]}
                for v in sections.records[:6]
            ],
            "same_page_only": True,
            "production_enabled": False,
        }
        if evidence["candidate_text_nodes"] < 4 or not evidence["recent_oct_2026"]:
            evidence["passed"] = False
        print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
        return 0 if evidence["passed"] else 1
    except Exception as error:
        print(json.dumps({"passed": False, "upstream": HOST, "failure_type": type(error).__name__}, sort_keys=True))
        return 1

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
