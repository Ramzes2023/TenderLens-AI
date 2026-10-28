import socket
import ssl
import unittest
import httpx
from scripts.source_failure_diagnostics import transport_category, worker_failure_code

class SafeFailureDiagnostics(unittest.TestCase):
    def test_nested_dns_and_tls_do_not_leak_messages(self):
        secret = 'https://private.invalid/?token=SECRET customer=PRIVATE'
        for cause, expected in [(socket.gaierror(secret), 'dns'),
                                (ssl.SSLCertVerificationError(secret), 'tls_certificate'),
                                (httpx.ConnectTimeout(secret), 'timeout')]:
            outer = RuntimeError(secret)
            outer.__cause__ = cause
            self.assertEqual(transport_category(outer), expected)

    def test_unknown_cycle_and_malicious_worker_code_stay_redacted(self):
        error = RuntimeError('SECRET')
        error.__cause__ = error
        self.assertEqual(transport_category(error), 'unclassified')
        self.assertEqual(worker_failure_code('SECRET'), 'unclassified')
        self.assertEqual(worker_failure_code('handler_error'), 'handler_error')
        self.assertEqual(worker_failure_code([]), 'unclassified')

if __name__ == '__main__':
    unittest.main()
