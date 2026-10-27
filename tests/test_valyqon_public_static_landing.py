"""Strict offline contracts for marketing-only Caddy landing; no cloud changes."""
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "ops" / "public_landing" / "site"
HTML = SITE / "index.html"
CSS = SITE / "valyqon-public-landing.css"
CADDY = ROOT / "ops" / "public_landing" / "Caddyfile"
OVERLAY = ROOT / "ops" / "public_landing" / "compose.static.yaml"
ORIGINAL_CADDY = ROOT / "Caddyfile"
ORIGINAL_COMPOSE = ROOT / "compose.public.yaml"


class Markup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.links = []
        self.ids = set()
        self.images = []
        self.headings = []
        self.scripts = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append(tag)
        if "id" in attrs:
            assert attrs["id"] not in self.ids
            self.ids.add(attrs["id"])
        if tag == "a":
            self.links.append(attrs.get("href"))
        if tag == "link":
            self.links.append(attrs.get("href"))
        if tag == "img":
            self.images.append(attrs.get("src"))
        if tag == "script":
            self.scripts.append(attrs.get("src"))


def test_static_page_is_self_contained_truthful_and_accessible():
    html = HTML.read_text(encoding="utf-8")
    parser = Markup()
    parser.feed(html)
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert 'lang="en"' in html
    assert 'name="viewport"' in html
    assert 'id="main"' in html
    assert 'id="hero-heading"' in html
    assert "ILLUSTRATIVE UI" in html
    assert "does not promise live alerts" in html
    assert "availability varies by source" in html.lower()
    assert parser.tags.count("h1") == 1
    assert "form" not in parser.tags
    assert "input" not in parser.tags
    assert "iframe" not in parser.tags
    assert not parser.scripts
    assert not parser.images
    assert "/register" not in parser.links
    assert "/login" in parser.links
    assert parser.links.count("/valyqon-public-landing.css") == 1
    assert all(link and (link.startswith("#") or link in {
        "/", "/login", "/valyqon-public-landing.css"
    }) for link in parser.links)
    assert "<script" not in html.lower()
    assert "fetch(" not in html
    assert not re.search(r"(https?://|javascript:|data:)[^\s\"']+", html, re.I)
    assert all(target in parser.ids for target in (
        "main", "product", "coverage", "method"
    ))
    assert len(html.encode("utf-8")) < 30_000


def test_stylesheet_is_bounded_and_does_not_use_external_sources():
    css = CSS.read_text(encoding="utf-8")
    assert "@media(max-width:680px)" in css
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert "focus-visible" in css
    assert "position:fixed" not in css.replace(" ", "")
    assert "url(" not in css.lower()
    assert "@import" not in css.lower()
    assert 1000 < len(css) < 18_000


def test_caddy_file_overrides_only_static_exact_paths():
    body = CADDY.read_text(encoding="utf-8")
    assert "{$TENDERLENS_DOMAIN}" in body
    assert "{$ACME_EMAIL}" in body
    assert "@public_home path /" in body
    assert "@public_css path /valyqon-public-landing.css" in body
    assert "rewrite * /index.html" in body
    assert "root * /srv/valyqon-public" in body
    assert body.count("file_server") == 2
    assert "reverse_proxy api:8000" in body
    assert "Content-Security-Policy" in body
    assert "default-src 'none'" in body
    assert "connect-src 'none'" in body
    assert "Cache-Control" in body
    assert body.count("handle {") == 1
    assert body.count("handle @public_home {") == 1
    assert body.count("handle @public_css {") == 1
    assert not any(word in body for word in ("redir", "tls_insecure_skip_verify", "php_fastcgi"))
    assert ORIGINAL_CADDY.read_text(encoding="utf-8").count("reverse_proxy api:8000") == 1


def test_release_overlay_changes_no_database_or_server_other_than_caddy_mounts():
    import yaml
    config = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
    assert list(config) == ["services"]
    assert list(config["services"]) == ["caddy"]
    assert set(config["services"]["caddy"]) == {"volumes"}
    mounts = config["services"]["caddy"]["volumes"]
    assert len(mounts) == 2
    assert all(v.endswith(":ro") for v in mounts)
    assert "./ops/public_landing/Caddyfile:/etc/caddy/Caddyfile:ro" in mounts
    assert "./ops/public_landing/site:/srv/valyqon-public:ro" in mounts
    existing = yaml.safe_load(ORIGINAL_COMPOSE.read_text(encoding="utf-8"))
    assert "api" in existing["services"] and "caddy" in existing["services"]
    assert "tenderlens_data" in existing["volumes"]
    assert not (set(config["services"]) & {"api", "bot", "connector-worker", "postgres", "mailpit"})
