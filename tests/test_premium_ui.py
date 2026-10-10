from html.parser import HTMLParser
from app.api.landing import landing_html
from app.api.auth_pages import login_html, register_html


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.anchors = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag == 'a' and attrs.get('href', '').startswith('#'):
            self.anchors.append(attrs['href'][1:])


def test_marketing_preview_is_labeled_and_navigation_targets_exist():
    html = landing_html()
    assert 'How discovery works' in html and 'No search has been run here' in html
    assert 'Credentials required' in html and 'Billing is not enabled' in html
    links = Links()
    links.feed(html)
    assert links.anchors and set(links.anchors) <= links.ids


def test_password_toggle_is_not_a_submit_and_auth_stays_generic():
    for html in (login_html(), register_html()):
        assert 'type="button" id="togglePassword"' in html
        assert 'aria-controls="password"' in html
        assert '← Back to VALYQON' in html
        assert 'j.detail' not in html
        assert 'credentials:' in html


def test_discovery_filters_have_one_owner_without_navigation_catalog():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    premium = (root / "app/api/static/premium.js").read_text(encoding="utf-8")
    discovery = (root / "app/api/static/discovery.js").read_text(encoding="utf-8")
    from app.api.discovery_ui import DISCOVERY_HTML
    for marker in ("filterSource", "filterCurrency", "hydrateDiscoveryCatalog",
                   "ensureOptions", "MutationObserver", "CURRENCIES", "SOURCES"):
        assert marker not in premium
    assert 'id="filterSource"' in DISCOVERY_HTML
    assert 'id="filterCurrency"' in DISCOVERY_HTML
    assert "options('filterSource',items.map(i=>i.source))" in discovery
    assert "options('filterCurrency',items.map(i=>i.currency))" in discovery
