"""Explicit presentation bindings for static public/auth copy; never customer data."""
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re

COPY = json.loads((Path(__file__).parent / 'static/public_copy.json').read_text(encoding='utf-8'))


class _Bindings(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if tag not in {'meta', 'link', 'input', 'br', 'hr', 'img'}:
            self.stack.append(tag)
        values = dict(attrs)
        extra = ''
        for attr in ('aria-label', 'placeholder'):
            value = values.get(attr)
            if value in COPY and f'data-public-{attr}' not in values:
                extra += f' data-public-{attr}="{escape(value, quote=True)}"'
        raw = self.get_starttag_text()
        self.output.append(raw[:-1] + extra + '>')

    def handle_endtag(self, tag):
        if tag in self.stack:
            self.stack = self.stack[:len(self.stack) - 1 - self.stack[::-1].index(tag)]
        self.output.append(f'</{tag}>')

    def handle_data(self, data):
        key = ' '.join(data.split())
        if key in COPY and not any(tag in self.stack for tag in ('script', 'style', 'title')):
            leading = data[:len(data) - len(data.lstrip())]
            trailing = data[len(data.rstrip()):]
            self.output.append(f'{leading}<span data-public-copy="{escape(key, quote=True)}">{escape(key)}</span>{trailing}')
        else:
            self.output.append(data if any(tag in self.stack for tag in ('script', 'style')) else escape(data))

    def handle_entityref(self, name):
        self.output.append(f'&{name};')

    def handle_charref(self, name):
        self.output.append(f'&#{name};')

    def handle_decl(self, decl):
        self.output.append(f'<!{decl}>')


def language_selector() -> str:
    uk = '<svg viewBox="0 0 60 30" aria-hidden="true"><path fill="#163b78" d="M0 0h60v30H0z"/><path stroke="#fff" stroke-width="6" d="m0 0 60 30M60 0 0 30"/><path stroke="#c8102e" stroke-width="2" d="m0 0 60 30M60 0 0 30"/><path stroke="#fff" stroke-width="10" d="M30 0v30M0 15h60"/><path stroke="#c8102e" stroke-width="6" d="M30 0v30M0 15h60"/></svg>'
    ru = '<svg viewBox="0 0 60 30" aria-hidden="true"><path fill="#fff" d="M0 0h60v10H0z"/><path fill="#1849a9" d="M0 10h60v10H0z"/><path fill="#d52b1e" d="M0 20h60v10H0z"/></svg>'
    return f'<div class="public-languages" role="group" aria-label="Language" data-public-aria-label="Language"><button type="button" data-public-locale="en" lang="en" aria-label="English">{uk} English</button><button type="button" data-public-locale="ru" lang="ru" aria-label="Русский">{ru} Русский</button></div>'


def public_html(html: str) -> str:
    parser = _Bindings()
    parser.feed(html)
    html = ''.join(parser.output)
    dictionary = json.dumps(COPY, ensure_ascii=False).replace('<', '\\u003c').replace('&', '\\u0026')
    assets = '<meta name="description" content="Global Procurement Intelligence powered by AI"><link rel="stylesheet" href="/assets/public.css?v=20261014">' + f'<script id="public-dictionary" type="application/json">{dictionary}</script><script src="/assets/public_locale.js?v=20261014"></script>'
    # Public language styles precede the final responsive override across all pages.
    responsive = re.findall(r'<link rel="stylesheet" href="/assets/responsive\\.css[^"]*">', html)
    if len(responsive) == 1:
        html = html.replace(responsive[0], '', 1)
        html = html.replace('</head>', assets + responsive[0] + '</head>')
    else:
        html = html.replace('</head>', assets + '</head>')
    if 'class="auth-premium"' in html or 'class="invitation-page"' in html:
        html = html.replace('<main class="card">', '<main class="card">' + language_selector(), 1)
        html = html.replace('</main>', '<div class="public-auth-help"><a href="/how-it-works" data-public-copy="How it works">How it works</a> · <a href="/usage-guidelines" data-public-copy="Usage guidelines">Usage guidelines</a></div></main>')
    return html.replace('</body>', '<script>PublicLocale.bind();</script></body>')
