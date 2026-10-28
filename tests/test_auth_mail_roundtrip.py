"""Full API/template/token roundtrip with intercepted TLS SMTP; never sends."""
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.auth import AuthRepository, AuthService
from app.auth.email_delivery import SMTPEmailSender


def test_verification_then_password_reset_through_actual_templates(tmp_path, monkeypatch):
    monkeypatch.setenv('VALYQON_LEGAL_REQUIRED', 'false')
    repository = AuthRepository(tmp_path / 'disposable.db')
    repository.initialize()
    service = AuthService(repository)
    sender = SMTPEmailSender(host='smtp.resend.com', port=465,
        from_address='VALYQON AI <noreply@valyqon.dns.army>',
        public_base_url='https://valyqon.duckdns.org', username='resend',
        password='re_OFFLINE_ONLY', ssl_enabled=True, starttls=False)
    messages = []
    def capture(message):
        messages.append(message)
        return {}
    def token(message, path):
        urls = [word for word in message.get_content().split() if word.startswith('https://')]
        assert len(urls) == 1
        url = urlsplit(urls[0])
        assert url.netloc == 'valyqon.duckdns.org' and url.path == path
        assert message['Date'] and message['Message-ID'].endswith('@valyqon.dns.army>')
        return parse_qs(url.query)['token'][0]
    runtime = ApiRuntime(auth_service=service, email_sender=sender)
    settings = ApiSettings(host='127.0.0.1', port=8000, reload=False, api_key=None)
    with patch('smtplib.SMTP', side_effect=AssertionError('Plain SMTP forbidden')), \
         patch('smtplib.SMTP_SSL') as tls:
        tls.return_value.__enter__.return_value.send_message.side_effect = capture
        with TestClient(create_app(runtime=runtime, settings=settings)) as client:
            email = 'controlled@example.invalid'
            old, new = 'original secure password 123', 'replacement secure password 456'
            assert client.post('/api/v1/auth/register', json={'email': email, 'password': old}).status_code == 201
            assert len(messages) == 1
            verification = token(messages[0], '/verify-email')
            assert client.post('/api/v1/auth/login', json={'email': email, 'password': old}).status_code == 403
            assert client.post('/api/v1/auth/verify-email', json={'token': verification}).status_code == 200
            identity = client.get('/api/v1/auth/me').json()
            assert client.post('/api/v1/auth/verify-email', json={'token': verification}).status_code == 422
            assert client.post('/api/v1/auth/forgot-password', json={'email': email}).status_code == 202
            assert len(messages) == 2
            reset = token(messages[1], '/reset-password')
            assert client.post('/api/v1/auth/reset-password', json={'token': reset, 'password': new}).status_code == 200
            assert client.get('/api/v1/auth/me').status_code == 401
            assert client.post('/api/v1/auth/reset-password', json={'token': reset, 'password': new}).status_code == 422
            assert client.post('/api/v1/auth/login', json={'email': email, 'password': old}).status_code == 401
            assert client.post('/api/v1/auth/login', json={'email': email, 'password': new}).status_code == 200
            assert client.get('/api/v1/auth/me').json() == identity
        assert tls.call_count == 2
