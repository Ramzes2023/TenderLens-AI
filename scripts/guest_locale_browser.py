"""Offline Chromium acceptance: real renderers/assets, synthetic auth responses, no settings/DB."""
import json
from pathlib import Path
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
package = types.ModuleType('app.api')
package.__path__ = [str(ROOT / 'app/api')]
sys.modules['app.api'] = package
from app.api.landing import landing_html
from app.api.public_help import help_html
from app.api.auth_pages import login_html, register_html, verify_email_html, forgot_password_html, reset_password_html
from app.api.invitation_page import invitation_page_html
from playwright.sync_api import sync_playwright

OUT = ROOT / 'artifacts/guest-i18n-ux-20261014_114337/local-results'
OUT.mkdir(exist_ok=True)
PAGES = {'/': landing_html, '/how-it-works': lambda: help_html('guide'), '/usage-guidelines': lambda: help_html('guidelines'), '/login': login_html, '/register': register_html, '/verify-email': verify_email_html, '/forgot-password': forgot_password_html, '/reset-password': reset_password_html, '/invite/synthetic': lambda: invitation_page_html('synthetic')}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path in PAGES:
            body, mime, status = PAGES[path]().encode(), 'text/html; charset=utf-8', 200
        elif path.startswith('/assets/'):
            file = ROOT / 'app/api/static' / Path(path).name
            body = file.read_bytes() if file.is_file() else b''
            mime = 'text/javascript' if file.suffix == '.js' else 'text/css'
            status = 200 if file.is_file() else 404
        else:
            body, mime, status = b'{}', 'application/json', 404
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.send_response(429)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"detail":"Synthetic rate limit"}')


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    results, failures, untranslated = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for locale in ('en', 'ru'):
            for width in (320, 390, 768, 1366):
                context = browser.new_context(viewport={'width': width, 'height': 900})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                for path in PAGES:
                    errors.clear()
                    scenario = f'{locale}/{width}/{path}'
                    try:
                        response = page.goto(base + path + '?lang=' + locale)
                        assert response.status == 200
                        assert page.locator('html').get_attribute('lang') == locale
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'horizontal overflow'
                        assert not errors, errors
                        assert page.locator('.public-languages svg').count() == (4 if path in ('/', '/how-it-works', '/usage-guidelines') else 2)
                        # Every visible binding has the exact current dictionary copy.
                        assert page.evaluate("""() => [...document.querySelectorAll('[data-public-copy]')].every(n => n.textContent === PublicLocale.t(n.dataset.publicCopy))""")
                        if locale == 'ru':
                            leftovers = page.evaluate("""() => {const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n, out=[];while(n=w.nextNode()){let e=n.parentElement,s=n.textContent.trim();if(e&&e.getClientRects().length&&!e.closest('script,style,[data-public-copy],.public-languages')&&/[a-z]{3}/i.test(s))out.push(s);}return out;}""")
                            allowed = ('VALYQON', 'Find. Analyze.', 'Score. Win.', 'TED', 'Find a Tender', 'CanadaBuys', 'AusTender', 'GETS', 'eTenders', 'CPPP', 'EIS', 'SAM.gov', 'Goszakup')
                            unknown = [s for s in leftovers if not any(a in s for a in allowed)]
                            untranslated.extend({'scenario': scenario, 'text': s} for s in unknown)
                            assert not unknown, unknown
                        if width in (390, 1366) and path in ('/', '/how-it-works', '/usage-guidelines', '/login', '/verify-email'):
                            page.screenshot(path=str(OUT / f'{locale}-{width}-{path.strip("/") or "landing"}.png'), full_page=True)
                        results.append({'scenario': scenario, 'result': 'PASS'})
                    except Exception as error:
                        failures.append({'scenario': scenario, 'error': str(error)})
                context.close()
        page = browser.new_page(viewport={'width': 390, 'height': 900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            page.goto(base)
            page.locator('#publicMenu').click()
            page.locator('[data-public-locale="ru"]:visible').first.focus()
            page.keyboard.press('Enter')
            assert page.locator('[data-public-locale="ru"]:visible').first.get_attribute('aria-pressed') == 'true'
            page.reload()
            assert page.locator('html').get_attribute('lang') == 'ru'
            page.locator('#publicMenu').click()
            page.locator('#publicNav a[href*="how-it-works"]').click()
            assert '/how-it-works' in page.url
            assert page.locator('html').get_attribute('lang') == 'ru'
            page.locator('header a[href*="register"]').click()
            page.fill('#email', 'synthetic@example.invalid')
            page.fill('#password', 'Synthetic-password-2026')
            page.locator('[data-public-locale="en"]:visible').first.click()
            assert page.input_value('#email') == 'synthetic@example.invalid'
            assert page.input_value('#password') == 'Synthetic-password-2026'
            page.locator('#submit').click()
            page.wait_for_function("document.getElementById('msg').textContent.includes('Too many')")
            page.locator('[data-public-locale="ru"]').click()
            assert 'Слишком много' in page.locator('#msg').inner_text()
            page.locator('.back-link').click()
            assert page.locator('html').get_attribute('lang') == 'ru'
            assert not errors, errors
            results.append({'scenario': 'keyboard/mobile/reload/cross-route/form-state/error-state', 'result': 'PASS'})
        except Exception as error:
            failures.append({'scenario': 'interactive journey', 'error': str(error)})
        # Storage-disabled browser follows browser locale and carries an explicit choice through links.
        context = browser.new_context(locale='ru-RU')
        context.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new Error('Storage disabled')}})")
        page = context.new_page()
        try:
            page.goto(base)
            assert page.locator('html').get_attribute('lang') == 'ru'
            page.locator('[data-public-locale="en"]:visible').first.click()
            page.locator('header a[href*="login"]').click()
            assert page.locator('html').get_attribute('lang') == 'en'
            page.reload()
            assert page.locator('html').get_attribute('lang') == 'en'
            results.append({'scenario': 'storage disabled/browser default/link persistence', 'result': 'PASS'})
        except Exception as error:
            failures.append({'scenario': 'storage disabled', 'error': str(error)})
        browser.close()
    server.shutdown()
    data = {'passed': len(results), 'failed': len(failures), 'skipped': 0, 'results': results, 'failures': failures, 'untranslated': untranslated}
    (OUT / 'browser.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': len(results), 'failed': len(failures), 'failures': failures}, ensure_ascii=True))
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
