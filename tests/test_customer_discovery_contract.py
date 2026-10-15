"""Static browser wiring, without importing the backend or opening a database."""
import ast
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.localized = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "a":
            self.links.append(attrs.get("href"))
        if "data-ui-en" in attrs:
            self.localized.append(attrs)


def test_customer_discovery_markup_and_shipped_handlers():
    tree = ast.parse((ROOT / "app/api/discovery_ui.py").read_text(encoding="utf-8"))
    html = next(ast.literal_eval(n.value) for n in tree.body
                if isinstance(n, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "DISCOVERY_HTML" for t in n.targets))
    parser = Markup()
    parser.feed(html)
    assert all(count == 1 for count in Counter(parser.ids).values())
    for key in ("discoveryGuide", "discoverySourceOutcomes", "discoverButton",
                "discoveryResults", "tenderDetail", "detailBody", "resetFilters"):
        assert key in parser.ids
    assert {"#companies", "#saved", "#monitoring"} <= set(parser.links)
    assert all(a.get("data-ui-ru") for a in parser.localized)
    js = (ROOT / "app/api/static/discovery.js").read_text(encoding="utf-8")
    assert "$('discoverButton').onclick=discover" in js
    assert "$('discoveryResults').onclick" in js
    assert "$('detailBody').onclick" in js
    assert "sourceOutcomes(data)" in js
    assert "/monitoring/scan" not in js  # Navigation is not a scan/subscription.
    assert "runSerial!==serial" in js
    shell = (ROOT / "app/api/saas_shell.py").read_text(encoding="utf-8")
    assert "/assets/discovery.js?v=phase24-customer-onepass" in shell
    assert "DISCOVERY_HTML," in shell
