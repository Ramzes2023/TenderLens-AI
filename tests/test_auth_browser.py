"""Chromium -> actual auth ASGI routes -> disposable SQLite; captured email only.

OFFLINE_FIXTURE delivery does not establish Mailpit or external SMTP delivery.
"""
from urllib.parse import urlsplit

import pytest


def test_registration_verification_reset_and_new_password_in_chromium(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    from fastapi.testclient import TestClient
    from app.api.config import ApiSettings
    from app.api.main import create_app
    from app.api.runtime import ApiRuntime
    from app.auth import AuthRepository, AuthService
    from tests.test_password_reset_api import FakeEmailSender

    repository = AuthRepository(tmp_path / "OFFLINE_FIXTURE-auth-browser.db")
    repository.initialize()
    service = AuthService(repository)
    sender = FakeEmailSender()
    sender.public_base_url = "http://testserver"
    runtime = ApiRuntime(auth_service=service, email_sender=sender)
    app = create_app(runtime=runtime, settings=ApiSettings('127.0.0.1', 0, False, None))
    responses = []
    with TestClient(app, follow_redirects=False) as client, playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))

            def dispatch(route):
                request = route.request
                if urlsplit(request.url).netloc != 'testserver':
                    route.abort()
                    return
                client.cookies.clear()
                response = client.request(request.method, request.url,
                                          headers=request.headers, content=request.post_data_buffer)
                responses.append((urlsplit(request.url).path, response.status_code))
                headers = {key: value for key, value in response.headers.items()
                           if key.lower() not in {'content-length', 'content-encoding', 'transfer-encoding'}}
                route.fulfill(status=response.status_code, headers=headers, body=response.content)

            page.route('**/*', dispatch)
            page.goto('http://testserver/register')
            page.fill('#email', 'OFFLINE_FIXTURE-browser@example.test')
            page.fill('#password', 'original secure password 123')
            for checkbox in ('#acceptOffer', '#acceptPersonal'):
                if page.locator(checkbox).count():
                    page.check(checkbox)
            page.click('#submit')
            page.wait_for_url('**/verify-email?email=*')
            assert responses[-1][1] == 200
            assert sender.messages[-1]['recipient'].lower() == 'offline_fixture-browser@example.test'
            page.goto(sender.messages[-1]['verification_url'])
            page.wait_for_url(lambda url: urlsplit(url).path == '/dashboard')
            page.goto('http://testserver/forgot-password')
            page.fill('#email', 'OFFLINE_FIXTURE-browser@example.test')
            with page.expect_response('**/api/v1/auth/forgot-password') as reset:
                page.click('#submit')
            assert reset.value.status == 202
            page.goto(sender.messages[-1]['reset_url'])
            page.fill('#password', 'replacement secure password 456')
            page.fill('#confirmPassword', 'replacement secure password 456')
            with page.expect_response('**/api/v1/auth/reset-password') as changed:
                page.click('#submit')
            assert changed.value.status == 200
            page.goto('http://testserver/login')
            page.fill('#email', 'OFFLINE_FIXTURE-browser@example.test')
            page.fill('#password', 'replacement secure password 456')
            page.click('#submit')
            page.wait_for_url(lambda url: urlsplit(url).path == '/dashboard')
            assert ('/api/v1/auth/register', 201) in responses
            assert ('/api/v1/auth/verify-email', 200) in responses
            assert ('/api/v1/auth/login', 200) in responses
            assert errors == []
        finally:
            browser.close()
