"""Disposable PR264 Docker browser/Mailpit acceptance on reserved QA ports only.

Requires the separate audit composition, never the review instance on 18865.
Does not seed tenders, call payment providers, or send external notifications.
"""
import json
import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import sync_playwright


def main():
    base = 'http://127.0.0.1:19865'
    mailpit = 'http://127.0.0.1:19866'
    email = f'qa-pr264-{secrets.token_hex(5)}@example.test'
    password = secrets.token_urlsafe(24)
    replacement = secrets.token_urlsafe(24)
    responses, errors = [], []
    with httpx.Client(trust_env=False, timeout=15) as http, sync_playwright() as p:
        assert http.get(base + '/health').status_code == 200
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': 1366, 'height': 900})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('response', lambda response: responses.append({
                'path': urlsplit(response.url).path, 'status': response.status}))
            page.goto(base + '/register')
            page.fill('#email', email)
            page.fill('#password', password)
            for checkbox in ('#acceptOffer', '#acceptPersonal'):
                if page.locator(checkbox).count():
                    page.check(checkbox)
            page.click('#submit')
            page.wait_for_url('**/verify-email?email=*')

            def captured_link(path):
                messages = http.get(mailpit + '/api/v1/messages').json()['messages']
                for message in messages:
                    if not any(recipient['Address'].lower() == email for recipient in message['To']):
                        continue
                    detail = http.get(mailpit + '/api/v1/message/' + message['ID']).json()
                    match = re.search(re.escape(base + path) + r'\?token=[A-Za-z0-9_\-]+',
                                      detail.get('Text', '') + detail.get('HTML', ''))
                    if match:
                        return match.group()
                raise AssertionError('Expected local Mailpit message missing')

            page.goto(captured_link('/verify-email'))
            page.wait_for_url(lambda url: urlsplit(url).path == '/dashboard')
            page.reload()
            page.wait_for_function("typeof state !== 'undefined' && state.accountId !== null")
            for route in ['overview', 'recommended', 'saved', 'tender-planner', 'monitoring',
                          'source-health', 'ai-analysis', 'notifications', 'billing', 'settings']:
                page.evaluate('(route) => {location.hash=route}', route)
                page.wait_for_timeout(100)
            page.goto(base + '/forgot-password')
            page.fill('#email', email)
            with page.expect_response('**/api/v1/auth/forgot-password') as reset:
                page.click('#submit')
            assert reset.value.status == 202
            page.goto(captured_link('/reset-password'))
            page.fill('#password', replacement)
            page.fill('#confirmPassword', replacement)
            with page.expect_response('**/api/v1/auth/reset-password') as changed:
                page.click('#submit')
            assert changed.value.status == 200
            page.goto(base + '/login')
            page.fill('#email', email)
            page.fill('#password', replacement)
            page.click('#submit')
            page.wait_for_url(lambda url: urlsplit(url).path == '/dashboard')
            page.set_viewport_size({'width': 390, 'height': 844})
            page.reload()
            page.wait_for_selector('#navToggle')
            page.click('#navToggle')
            assert page.locator('#navToggle').get_attribute('aria-expanded') == 'true'
            page.keyboard.press('Escape')
            assert page.locator('#navToggle').get_attribute('aria-expanded') == 'false'
            assert not errors, errors
            evidence = dict(level='LOCAL_DOCKER_BROWSER_MAILPIT',
                            synthetic_tenders_inserted=0, page_errors=errors,
                            mailpit_verification_and_reset=True, responses=responses)
            Path('artifacts/audit-pr264-docker-browser.json').write_text(
                json.dumps(evidence, indent=2), encoding='utf-8')
            print('PASS: Docker Chromium registration, Mailpit verification/reset, login, refresh, navigation, mobile menu; no JS exceptions')
        finally:
            browser.close()


if __name__ == '__main__':
    main()
