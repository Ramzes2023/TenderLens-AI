"""Read-only bounded official RZD e-shop public procurement HTML diagnostic.

Research only. Never scores or writes to production. No credentials, cookies,
follow redirects, proxy, TLS exceptions, dynamic URL hosts, or unrestricted GETs.
"""
from __future__ import annotations

from html.parser import HTMLParser
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, ProxyHandler, HTTPRedirectHandler

HOST = "eshoprzd.ru"
LIST_URL = "https://eshoprzd.ru/"
URL_REGEX = re.compile(r"^/purchases/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/?$", re.I)
CAP = 1_200_000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Extract(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.current_link = None
        self.links = []
        self.headings = []
        self.head = None
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.current_link = [attrs.get("href", ""), []]
        if tag in {"h1", "h2", "h3", "h4"}:
            self.head = [tag, []]
        if tag == "title":
            self.in_title = True

    def handle_data(self, data):
        if self.current_link is not None:
            self.current_link[1].append(data)
        if self.head is not None:
            self.head[1].append(data)
        if self.in_title:
            self.title.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current_link is not None:
            self.links.append((self.current_link[0], " ".join(" ".join(self.current_link[1]).split())[:210]))
            self.current_link = None
        if self.head is not None and tag == self.head[0]:
            self.headings.append((tag, " ".join(" ".join(self.head[1]).split())[:240]))
            self.head = None
        if tag == "title":
            self.in_title = False


def canonical(href):
    if not isinstance(href, str) or not href or "\\" in href or any(c.isspace() or ord(c) < 32 for c in href):
        return None
    target = urljoin(LIST_URL, href)
    p = urlsplit(target)
    if p.scheme != "https" or p.hostname != HOST or p.netloc != HOST or p.query or p.fragment:
        return None
    m = URL_REGEX.fullmatch(p.path)
    return (m.group(1), target) if m else None


def get_page(url):
    p = urlsplit(url)
    if p.scheme != "https" or p.netloc != HOST or p.query or p.fragment or url not in {LIST_URL, *[u for _, u in urls[:3]]}:
        raise ValueError("Unapproved read-only research URL")
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html", "Accept-Encoding": "identity"})
    with opener.open(request, timeout=17) as response:
        if response.status != 200 or "html" not in response.headers.get("content-type", "").lower():
            raise ValueError("Official HTML unavailable")
        data = response.read(CAP + 1)
    if not 0 < len(data) <= CAP:
        raise ValueError("Official HTML size outside bound")
    return data.decode("utf-8-sig", "replace"), len(data)


def main():
    global urls
    urls = []
    try:
        html, size = get_page(LIST_URL)
        parsed = Extract()
        parsed.feed(html)
        for href, txt in parsed.links:
            found = canonical(href)
            if found is not None and found not in urls:
                urls.append(found)
        print("RZD_LIST_HTTP=200")
        print("RZD_LIST_BYTES=" + str(size))
        print("RZD_LINKS_TOTAL=" + str(len(parsed.links)))
        print("RZD_REAL_PURCHASE_UUID_LINKS=" + str(len(urls)))
        print("RZD_LIST_HEADINGS=" + repr(parsed.headings[:8]))
        print("RZD_LIST_PURCHASE_URLS=" + repr(urls[:3]))
        print("RZD_LIST_VISIBLE_LINK_TITLES=" + repr([(canonical(h), t) for h,t in parsed.links if canonical(h)][:4]))
        ok = 0
        for identifier, link in urls[:3]:
            page, count = get_page(link)
            doc = Extract()
            doc.feed(page)
            h = [v for tag,v in doc.headings if tag in {"h1", "h2", "h3"}]
            idMatch = re.search(r"Ценовой запрос\s*№\s*(\d{3,12})", " ".join(h))
            print("RZD_DETAIL_HTTP_200=" + repr({"uuid":identifier,"bytes":count,"heading":h[:4],"visible_request_number":idMatch.group(1) if idMatch else None}))
            if idMatch and h:
                ok += 1
        print("RZD_INDEPENDENT_DETAILS=" + str(ok))
        if len(urls) < 2 or ok < 2:
            print("RZD_RESEARCH=BLOCKED_INCOMPLETE_LIVE_DETAIL")
            return 2
        print("RZD_RESEARCH=PASS_PUBLIC_CANDIDATE_NOT_INTEGRATED")
        return 0
    except (HTTPError, URLError, ValueError, TimeoutError, OSError) as exc:
        print("RZD_RESEARCH=BLOCKED_" + type(exc).__name__)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
