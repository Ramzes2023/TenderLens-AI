"""Real bilingual auth journeys against isolated SQLite and fake mail, entirely loopback."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright


def main():
    spec = importlib.util.spec_from_file_location('synthetic_api_fixture', ROOT / 'tests/test_private_preview_api.py')
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)
    out = ROOT / 'artifacts/guest-i18n-ux-20261014_114337/local-results'
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for locale in ('ru', 'en'):
            fixture = fixture_module.PrivatePreviewApiTests()
            fixture.setUp()
            lock = threading.Lock()
            statuses = []

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def handle_request(self):
                    with lock:
                        fixture.client.cookies.clear()
                        headers = {key: value for key, value in self.headers.items() if key.lower() not in ('connection', 'content-length')}
                        content = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                        response = fixture.client.request(self.command, self.path, headers=headers, content=content, follow_redirects=False)
                    statuses.append({'path': '/invite/synthetic' if self.path.startswith('/invite/') else urlsplit(self.path).path, 'status': response.status_code})
                    self.send_response(response.status_code)
                    for key, value in response.headers.multi_items():
                        if key.lower() not in ('content-length', 'content-encoding', 'transfer-encoding', 'connection'):
                            self.send_header(key, value)
                    self.end_headers()
                    try:
                        self.wfile.write(response.content)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        pass  # A page navigation can cancel an in-flight synthetic asset/API response.

                do_GET = handle_request
                do_POST = handle_request

            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            context = browser.new_context(viewport={'width': 390, 'height': 844})
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(base + '/?lang=' + locale)
                page.locator('header a[href*="register"]').click()
                assert page.locator('html').get_attribute('lang') == locale
                page.fill('#email', 'journey@example.test')
                page.fill('#password', fixture_module.PASSWORD)
                with page.expect_response('**/api/v1/auth/register') as registration:
                    page.click('#submit')
                assert registration.value.status == 201
                page.wait_for_url(lambda url: urlsplit(url).path == '/verify-email')
                assert page.locator('html').get_attribute('lang') == locale
                assert page.input_value('#verifyEmail') == 'journey@example.test'
                page.locator('[data-public-locale="' + ('en' if locale == 'ru' else 'ru') + '"]').click()
                assert page.input_value('#verifyEmail') == 'journey@example.test'
                page.locator('[data-public-locale="' + locale + '"]').click()
                # Login before verification follows the existing 403 verification gate.
                page.goto(base + '/login')
                page.fill('#email', 'journey@example.test')
                page.fill('#password', fixture_module.PASSWORD)
                page.click('#submit')
                page.wait_for_url(lambda url: urlsplit(url).path == '/verify-email')
                assert page.locator('html').get_attribute('lang') == locale
                with page.expect_response('**/api/v1/auth/resend-verification') as resend:
                    page.click('#resend')
                assert resend.value.status == 202
                token = parse_qs(urlsplit(fixture.sender.messages[-1]['verification_url']).query)['token'][0]
                page.goto(base + '/verify-email?token=' + token)
                page.wait_for_url(lambda url: urlsplit(url).path == '/dashboard', timeout=15000)
                assert page.locator('#shellLocale').input_value() == locale
                # Leave the authenticated shell before logout so its in-flight account bootstrap cannot redirect the recovery page.
                page.goto(base + '/')
                assert page.evaluate("fetch('/api/v1/auth/logout',{method:'POST',credentials:'same-origin'}).then(r=>r.status)") == 204
                page.goto(base + '/forgot-password')
                page.fill('#email', 'journey@example.test')
                with page.expect_response('**/api/v1/auth/forgot-password') as forgot:
                    page.click('#submit')
                assert forgot.value.status == 202
                page.wait_for_function("getComputedStyle(document.getElementById('msg')).display!=='none'")
                assert page.locator('#msg').inner_text().startswith('Если' if locale == 'ru' else 'If an eligible')
                token = parse_qs(urlsplit(fixture.sender.messages[-1]['reset_url']).query)['token'][0]
                page.goto(base + '/reset-password?token=' + token)
                assert 'token=' not in page.url
                assert page.locator('html').get_attribute('lang') == locale
                replacement = 'Synthetic replacement password 54321'
                page.fill('#password', replacement)
                page.fill('#confirmPassword', 'Mismatched synthetic password 123')
                page.click('#submit')
                assert page.locator('#msg').inner_text() == ('Пароли должны совпадать.' if locale == 'ru' else 'Passwords must match.')
                page.locator('[data-public-locale="' + ('en' if locale == 'ru' else 'ru') + '"]').click()
                assert page.input_value('#password') == replacement
                page.locator('[data-public-locale="' + locale + '"]').click()
                page.fill('#confirmPassword', replacement)
                with page.expect_response('**/api/v1/auth/reset-password') as reset:
                    page.click('#submit')
                assert reset.value.status == 200
                page.wait_for_url(lambda url: urlsplit(url).path == '/login')
                assert page.locator('html').get_attribute('lang') == locale
                page.fill('#email', 'journey@example.test')
                page.fill('#password', replacement)
                with page.expect_response('**/api/v1/auth/login') as login:
                    page.click('#submit')
                assert login.value.status == 200
                page.wait_for_url(lambda url: urlsplit(url).path == '/dashboard')
                assert page.locator('#shellLocale').input_value() == locale
                page.goto(base + '/')
                assert page.locator('html').get_attribute('lang') == locale
                assert not errors, errors
                assert not any(item['status'] >= 500 for item in statuses)
                page.screenshot(path=str(out / f'{locale}-authenticated-return-guest.png'), full_page=True)
                results.append({'locale': locale, 'result': 'PASS', 'page_errors': errors, 'responses': statuses})
            finally:
                context.close()
                server.shutdown()
                fixture.doCleanups()
        browser.close()
    (out / 'bilingual-auth.json').write_text(json.dumps({'passed': len(results), 'failed': 0, 'skipped': 0, 'journeys': results}, indent=2), encoding='utf-8')
    print('Bilingual real auth: 2 PASS, 0 FAIL, 0 SKIP (register, unverified login gate, resend, verify, forgot, reset, login, return guest)')


if __name__ == '__main__':
    main()
