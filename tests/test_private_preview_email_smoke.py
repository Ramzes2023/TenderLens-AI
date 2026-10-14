"""Offline fixtures only; never connect to a live mailbox."""
import unittest
from unittest.mock import patch
from ops.private_preview.browser_smoke import email_link, preview_path, SmokeFailure

BASE = 'http://127.0.0.1:18765'
MAIL = 'http://127.0.0.1:18766'
EMAIL = 'preview-synthetic@example.test'


class Response:
    status = 200

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


class Mailbox:
    def __init__(self, body, paginated=False):
        self.body, self.paginated, self.reads = body, paginated, []

    def get(self, url, **kwargs):
        self.reads.append(url)
        ours = {'ID': 'ours', 'To': [{'Address': EMAIL.upper()}]}
        other = {'ID': 'owner', 'To': [{'Address': 'unrelated@example.test'}]}
        if url.endswith('/messages'):
            return Response({'messages': [other] if self.paginated else [other, ours], 'total': 2})
        if '?start=1' in url:
            return Response({'messages': [ours]})
        if url.endswith('/owner'):
            raise AssertionError('unrelated body read')
        return Response(self.body)


class EmailAcceptanceTests(unittest.TestCase):
    def lookup(self, mailbox, report=lambda value: None):
        return email_link(mailbox, MAIL, BASE, EMAIL, '/verify-email', report)

    def test_html_pagination_exact_recipient_safe_diagnostics(self):
        mailbox = Mailbox({'Text': '', 'HTML': '<a href="' + BASE +
                          '/verify-email?token=fixture&amp;next=%2Fdashboard">Verify</a>'}, True)
        diagnostics = []
        self.assertIn('token=fixture&next=', self.lookup(mailbox, diagnostics.append))
        self.assertEqual(diagnostics, ['MAILPIT_API_RESPONSIVE=VERIFIED',
            'MATCHING_SYNTHETIC_VERIFICATION_MESSAGE_FOUND=VERIFIED', 'VALID_VERIFY_LINK_FOUND=VERIFIED'])
        self.assertNotIn(EMAIL, str(diagnostics))
        self.assertNotIn('fixture', str(diagnostics))
        self.assertFalse(any(url.endswith('/owner') for url in mailbox.reads))

    def test_invalid_tokens_and_foreign_origin_rejected(self):
        for suffix in ('?token=', '?token=a&token=b'):
            with self.assertRaises(SmokeFailure):
                self.lookup(Mailbox({'Text': BASE + '/verify-email' + suffix}))
        with self.assertRaises(SmokeFailure):
            self.lookup(Mailbox({'Text': 'http://localhost:9999/verify-email?token=fixture'}))

    def test_matching_message_without_link_is_content_failure(self):
        with patch('ops.private_preview.browser_smoke.time.monotonic', side_effect=[0, 0, 31]), \
                patch('ops.private_preview.browser_smoke.time.sleep'):
            with self.assertRaisesRegex(SmokeFailure, 'content/parsing failure'):
                self.lookup(Mailbox({'Text': 'No verification link'}))

    def test_api_timeout_redacted_and_distinct_from_missing_delivery(self):
        mailbox = Mailbox({})
        with patch.object(mailbox, 'get', side_effect=TimeoutError('sensitive-token-url')):
            with self.assertRaisesRegex(SmokeFailure, 'listing request failed') as error:
                self.lookup(mailbox)
        self.assertNotIn('sensitive', str(error.exception))

    def test_unrelated_mail_is_true_missing_delivery_failure(self):
        mailbox = Mailbox({})
        with patch.object(mailbox, 'get', return_value=Response({'messages': [
                {'ID': 'owner', 'To': [{'Address': 'unrelated@example.test'}]}]})) as get, \
                patch('ops.private_preview.browser_smoke.time.monotonic', side_effect=[0, 0, 31]), \
                patch('ops.private_preview.browser_smoke.time.sleep'):
            with self.assertRaisesRegex(SmokeFailure, 'BLOCKED delivery/environment'):
                self.lookup(mailbox)
        self.assertEqual(get.call_count, 1)

    def test_locale_destination_keeps_origin_path_query_checks(self):
        for suffix in ('', '?lang=ru', '?lang=en'):
            self.assertTrue(preview_path(BASE + '/dashboard' + suffix, BASE, '/dashboard'))
        for url in (BASE + '/dashboard?token=fixture', BASE + '/dashboard?lang=xx',
                    BASE + '/login', 'http://localhost:9999/dashboard'):
            self.assertFalse(preview_path(url, BASE, '/dashboard'))
