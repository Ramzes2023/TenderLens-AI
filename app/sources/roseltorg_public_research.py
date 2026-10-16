"""Fail-closed read-only validation of Roseltorg public procedure details.

Research-stage only. Not registered in the production source catalog.
A discoverable listing and real worker -> database -> search gate are still required.
"""
from __future__ import annotations

from html.parser import HTMLParser
import re
from urllib.parse import urlsplit

HOST = "www.roseltorg.ru"
_PATH = re.compile(r"/procedure/([A-Z0-9]{8,24})")
_MAX_BYTES = 1_800_000


class _ProcedureText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        text = " ".join(data.split())
        if text:
            self.parts.append(text)


def parse_roseltorg_public_detail(payload: bytes, url: str):
    """Return an observed exact procedure ID and title, never inferred fields."""
    if type(payload) is not bytes or not 0 < len(payload) <= _MAX_BYTES or b"\x00" in payload:
        raise ValueError("Invalid Roseltorg HTML response")
    parts = urlsplit(url)
    match = _PATH.fullmatch(parts.path)
    if (parts.scheme != "https" or parts.netloc != HOST or match is None
            or parts.query or parts.fragment or parts.username or parts.password
            or parts.port is not None):
        raise ValueError("Noncanonical Roseltorg detail URL")
    identity = match.group(1)
    parser = _ProcedureText()
    parser.feed(payload.decode("utf-8-sig", "replace"))
    parser.close()
    text = " ".join(parser.parts)
    # Both the procedure marker and the exact number must appear as actual page text.
    if not re.search(r"Процедура\s*:\s*" + re.escape(identity) + r"(?![A-Z0-9])", text):
        raise ValueError("Roseltorg procedure identity not independently visible")
    m = re.search(r"Наименование\s+процедуры\s+(.+?)\s+(?:Организатор\s+торгов|Способ\s+проведения|Торговая\s+секция)", text)
    if m is None:
        raise ValueError("Roseltorg procedure title not independently visible")
    title = " ".join(m.group(1).split())
    if not 5 <= len(title) <= 1000:
        raise ValueError("Roseltorg procedure title is invalid")
    return {"source": "roseltorg_public_research", "external_id": identity,
            "title": title, "url": url}
