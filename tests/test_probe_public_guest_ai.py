"""Offline falsification tests for one-request public AI diagnostic."""
import json
import unittest

from scripts.probe_public_guest_ai import classify, classify_health, URL, HOST, QUESTION


class PublicAIDiagnosticTests(unittest.TestCase):
    def test_fixed_public_host_no_secrets(self):
        self.assertEqual(HOST, "valyqon.duckdns.org")
        self.assertEqual(URL, "https://valyqon.duckdns.org/api/v1/public/help/ask")
        self.assertIn("гостевой", QUESTION)

    def test_real_answer_only_from_verified_public_contract(self):
        success = json.dumps({"answer": "Гостевой поиск показывает доступные записи.",
                              "scope": "public_product_only"}).encode()
        self.assertEqual(classify(200, success), "LIVE_ANSWER_VERIFIED")
        for payload in [b"", b"not-json", b"{}",
                        b'{"scope":"public_product_only","answer":""}',
                        b'{"scope":"internal","answer":"yes"}']:
            self.assertEqual(classify(200, payload), "UNEXPECTED_SUCCESS_PAYLOAD")

    def test_exact_known_server_failure_classification(self):
        cases = {
            "Public AI help is not enabled.": "FEATURE_DISABLED",
            "Public AI help is not configured.": "PROVIDER_MISSING",
            "Public AI help is temporarily unavailable.": "PROVIDER_REQUEST_FAILED",
        }
        for detail, expected in cases.items():
            self.assertEqual(classify(503, json.dumps({"detail": detail}).encode()), expected)
        self.assertEqual(classify(503, b"hidden failure"), "SERVICE_UNAVAILABLE_UNKNOWN")

    def test_health_only_claims_configured_not_live_inference(self):
        configured = json.dumps({"components": {"llm": "ready"}}).encode()
        absent = json.dumps({"components": {"llm": "unavailable"}}).encode()
        self.assertEqual(classify_health(200, configured), "CONFIGURED_NOT_LIVE_VERIFIED")
        self.assertEqual(classify_health(200, absent), "PROVIDER_NOT_CONFIGURED")
        self.assertEqual(classify_health(200, b"not json"), "HEALTH_UNAVAILABLE")
        self.assertEqual(classify_health(503, configured), "HEALTH_UNAVAILABLE")

    def test_legacy_route_abuse_and_proxy_statuses(self):
        cases = {
            401: "AUTH_GATE_UNEXPECTED", 403: "ORIGIN_REJECTED",
            404: "ROUTE_NOT_DEPLOYED", 405: "METHOD_REJECTED",
            422: "REQUEST_REJECTED", 429: "PUBLIC_RATE_LIMITED",
            502: "PROXY_BAD_GATEWAY", 504: "PROXY_TIMEOUT",
            301: "UNEXPECTED_HTTP_STATUS",
        }
        for status, expected in cases.items():
            self.assertEqual(classify(status, b"<html>possibly secret</html>"), expected)


if __name__ == "__main__":
    unittest.main()
