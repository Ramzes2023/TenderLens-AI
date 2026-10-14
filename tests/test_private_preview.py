"""Offline preview safety, signed sessions and smoke-tool contract checks."""
from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.auth import AuthRepository, AuthService, EmailVerificationInvalid, PasswordResetInvalid
from app.auth.email_delivery import load_email_sender_from_env
from ops.private_preview.preview_app import SignedPreviewAuth
from ops.private_preview.browser_smoke import origin, email_link, SmokeFailure
from ops.private_preview.generate_env import generate

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops/private_preview"
PASSWORD = "Synthetic password 123456"


class PreviewSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repository = AuthRepository(Path(self.tmp.name) / "auth.db")
        self.repository.initialize()
        self.service = SignedPreviewAuth(AuthService(self.repository), "a" * 64)
        self.account = self.service.register("preview@example.test", PASSWORD)
        token, _ = self.service.issue_email_verification(self.account)
        self.account = self.service.verify_email(token)

    def test_signed_session_tamper_secret_rotation_and_logout(self):
        token = self.service.create_session(self.account)
        self.assertEqual(self.service.account_for_token(token).id, self.account.id)
        self.assertIsNone(self.service.account_for_token(token[:-1] + ("a" if token[-1] != "a" else "b")))
        other = SignedPreviewAuth(AuthService(self.repository), "b" * 64)
        self.assertIsNone(other.account_for_token(token))
        self.assertIsNone(self.service.account_for_token(token.split(".")[0]))
        self.service.logout(token)
        self.assertIsNone(self.service.account_for_token(token))

    def test_reset_revokes_signed_sessions_and_ticket_is_one_use(self):
        session = self.service.create_session(self.account)
        ticket, _ = self.service.issue_password_reset(self.account)
        self.service.reset_password(ticket, "Synthetic replacement 987654")
        self.assertIsNone(self.service.account_for_token(session))
        with self.assertRaises(PasswordResetInvalid):
            self.service.reset_password(ticket, PASSWORD)

    def test_expired_session_and_reset_fail_closed(self):
        session = self.service.create_session(self.account)
        ticket, _ = self.service.issue_password_reset(self.account)
        with closing(self.repository._connect()) as connection, connection:
            connection.execute("UPDATE auth_sessions SET expires_at=?", ("2000-01-01T00:00:00+00:00",))
            connection.execute("UPDATE auth_password_resets SET expires_at=?", ("2000-01-01T00:00:00+00:00",))
        self.assertIsNone(self.service.account_for_token(session))
        with self.assertRaises(PasswordResetInvalid):
            self.service.reset_password(ticket, PASSWORD)

    def test_verification_expired_and_consumed_tokens_rejected(self):
        account = self.service.register("second@example.test", PASSWORD)
        token, _ = self.service.issue_email_verification(account)
        with closing(self.repository._connect()) as connection, connection:
            connection.execute("UPDATE auth_email_verifications SET expires_at=? WHERE account_id=?",
                               ("2000-01-01T00:00:00+00:00", account.id))
        with self.assertRaises(EmailVerificationInvalid):
            self.service.verify_email(token)
        token, _ = self.service.issue_email_verification(account, enforce_cooldown=False)
        self.service.verify_email(token)
        with self.assertRaises(EmailVerificationInvalid):
            self.service.verify_email(token)

    def test_short_secret_rejected(self):
        with self.assertRaises(ValueError):
            SignedPreviewAuth(AuthService(self.repository), "short")

    def test_malformed_cookie_does_not_crash_guest(self):
        for value in ('opaque.é', 'opaque.' + 'é' * 64, 'a' * 300, '', None):
            self.assertIsNone(self.service.account_for_token(value))


class PreviewScaffoldTests(unittest.TestCase):
    def test_real_smtp_sender_formats_both_one_time_links_for_capture(self):
        import os
        with patch.dict(os.environ, {
            'VALYQON_EMAIL_MODE': 'smtp', 'VALYQON_SMTP_HOST': 'mailpit',
            'VALYQON_SMTP_PORT': '1025', 'VALYQON_SMTP_FROM': 'preview@example.test',
            'VALYQON_SMTP_STARTTLS': 'false', 'VALYQON_SMTP_SSL': 'false',
            'VALYQON_PUBLIC_BASE_URL': 'http://127.0.0.1:18765',
        }, clear=True), patch('smtplib.SMTP') as smtp:
            sender = load_email_sender_from_env()
            expiry = '2026-10-13T20:00:00+00:00'
            sender.send_verification(recipient='customer@example.test',
                                     verification_url=sender.public_base_url + '/verify-email?token=synthetic',
                                     expires_at=expiry)
            sender.send_password_reset(recipient='customer@example.test',
                                       reset_url=sender.public_base_url + '/reset-password?token=synthetic',
                                       expires_at=expiry)
            client = smtp.return_value.__enter__.return_value
            self.assertEqual(client.send_message.call_count, 2)
            messages = [call.args[0] for call in client.send_message.call_args_list]
            self.assertIn('/verify-email?token=synthetic', messages[0].get_content())
            self.assertIn('/reset-password?token=synthetic', messages[1].get_content())
            self.assertTrue(all(message['To'] == 'customer@example.test' for message in messages))
            self.assertTrue(all(expiry in message.get_content() for message in messages))
            client.starttls.assert_not_called()
            client.login.assert_not_called()

    def test_compose_isolated_services_and_ports(self):
        import re
        compose = (OPS / "compose.yaml").read_text()
        service_block = compose.split("networks:\n  isolated:")[0]
        self.assertEqual(re.findall(r"^  ([a-z]+):$", service_block, re.M), ["api", "db", "mailpit"])
        self.assertEqual(re.findall(r'"(127\.0\.0\.1:[0-9]+:[0-9]+)"', compose),
                         ["127.0.0.1:18765:8000", "127.0.0.1:18766:8025"])
        for forbidden in ("container_name:", "network_mode:", "privileged:", "external:", "docker.sock", "/opt/", "443:"):
            self.assertNotIn(forbidden, compose)
        self.assertIn("internal: true", compose)
        self.assertIn("image: postgres:16", compose)
        self.assertIn("${PREVIEW_DB_PASSWORD:?", compose)
        self.assertIn("${PREVIEW_APP_SECRET:?", compose)
        self.assertEqual(re.findall(r"mem_limit: (\d+)m", compose), ["512", "256", "128"])
        self.assertEqual(re.findall(r"^      - (.*):/", compose, re.M), ["preview_db"])

    def test_image_source_allowlist_includes_migrations_and_assets(self):
        ignore = (OPS / "Dockerfile.preview.dockerignore").read_text()
        self.assertIn("\n**\n", ignore)
        self.assertIn("!app/database/schema/*.sql", ignore)
        self.assertIn("!app/api/static/**", ignore)
        self.assertIn("!app/analytics/*.json", ignore)
        dockerfile = (OPS / "Dockerfile.preview").read_text()
        self.assertNotIn("COPY . ", dockerfile)
        self.assertIn("--factory", dockerfile)
        self.assertIn("--no-access-log", dockerfile)

    def test_generated_env_is_unique_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preview.env"
            generate(path)
            contents = path.read_text()
            values = dict(line.split("=", 1) for line in contents.splitlines())
            self.assertEqual(set(values), {"PREVIEW_DB_PASSWORD", "PREVIEW_APP_SECRET"})
            self.assertTrue(all(len(value) == 64 for value in values.values()))
            self.assertNotEqual(values['PREVIEW_DB_PASSWORD'], values['PREVIEW_APP_SECRET'])
            with self.assertRaises(FileExistsError):
                generate(path)
            self.assertEqual(path.read_text(), contents)

    def test_smoke_refuses_external_origins(self):
        self.assertEqual(origin("http://127.0.0.1:18765/"), "http://127.0.0.1:18765")
        for value in ("https://example.com", "http://example.com:18765", "http://user@localhost:18765", "http://localhost:18765/path"):
            with self.assertRaises(SmokeFailure):
                origin(value)

    def test_mailbox_reads_only_run_recipient_and_trusted_link(self):
        class Response:
            status = 200
            def __init__(self, value):
                self.value = value
            def json(self):
                return self.value
        class Mailbox:
            def __init__(self, link):
                self.link = link
                self.reads = []
            def get(self, url, **kwargs):
                self.reads.append(url)
                if url.endswith('/messages'):
                    return Response({'messages': [
                        {'ID': 'other', 'To': [{'Address': 'other@example.test'}]},
                        {'ID': 'ours', 'To': [{'Address': 'preview@example.test'}]},
                    ]})
                return Response({'Text': self.link})
        mailbox = Mailbox('http://127.0.0.1:18765/verify-email?token=synthetic')
        self.assertTrue(email_link(mailbox, 'http://127.0.0.1:18766', 'http://127.0.0.1:18765',
                                  'preview@example.test', '/verify-email').endswith('token=synthetic'))
        self.assertFalse(any(url.endswith('/other') for url in mailbox.reads))
        mailbox.link = 'https://example.com/verify-email?token=synthetic'
        with self.assertRaises(SmokeFailure):
            email_link(mailbox, 'http://127.0.0.1:18766', 'http://127.0.0.1:18765',
                       'preview@example.test', '/verify-email')

    def test_missing_mail_is_a_failure_not_a_skip(self):
        class Empty:
            status = 200
            def json(self):
                return {'messages': []}
        class Mailbox:
            def get(self, *args, **kwargs):
                return Empty()
        with patch('ops.private_preview.browser_smoke.time.monotonic', side_effect=[0, 0, 31]), \
             patch('ops.private_preview.browser_smoke.time.sleep'):
            with self.assertRaisesRegex(SmokeFailure, 'no matching test email'):
                email_link(Mailbox(), 'http://127.0.0.1:18766', 'http://127.0.0.1:18765',
                           'preview@example.test', '/verify-email')


if __name__ == '__main__':
    unittest.main()
