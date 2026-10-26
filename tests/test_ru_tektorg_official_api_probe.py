"""Offline-only safety contract for official TEK-Torg API transport diagnostics."""
import unittest
from unittest.mock import patch

from scripts import ru_tektorg_official_api_probe as api


class Response:
    def __init__(self, status=200, payload=b'{"resources":[]}', mime="application/json"):
        self.status, self.payload, self.mime = status, payload, mime

    def read(self, length):
        assert length == api.MAX_BYTES + 1
        return self.payload

    def getheader(self, key, default=""):
        assert key == "content-type"
        return self.mime


class FakeConnection:
    def __init__(self, response, calls):
        self.response, self.calls = response, calls

    def request(self, method, path, *, headers):
        self.calls.append((method, path, headers))
        assert method == "GET"
        assert headers.get("Accept-Encoding") == "identity"
        assert headers.get("Connection") == "close"
        assert not any(x in headers for x in ("Authorization", "Cookie", "Proxy-Authorization"))

    def getresponse(self):
        return self.response

    def close(self):
        self.calls.append(("close",))


class TEKOfficialApiSafety(unittest.TestCase):
    def test_fixed_official_api_paths_are_unique_and_complete(self):
        self.assertEqual(api.HOST, "api.tektorg.ru")
        self.assertEqual(api.TARGETS, {
            "directory": ("/", "json"),
            "sections": ("/lists/sections", "json"),
            "procedures_wsdl": ("/procedures/wsdl", "xml"),
        })
        self.assertEqual(len(set(api.TARGETS.values())), 3)

    def test_dtd_and_fake_login_are_not_api_procedure_document(self):
        self.assertTrue(api.authentic_document("json", b'{"resources":[]}', "application/json"))
        self.assertTrue(api.authentic_document("xml",
            b'<definitions xmlns="http://schemas.xmlsoap.org/wsdl/"/>', "text/xml"))
        self.assertFalse(api.authentic_document("xml",
            b'<!DOCTYPE definitions [<!ENTITY p "secret">]><definitions/>',
            "application/xml"))
        self.assertFalse(api.authentic_document("xml", b"<html>login</html>", "text/html"))
        self.assertFalse(api.authentic_document("json", b"<html>login</html>", "application/json"))
        self.assertFalse(api.authentic_document("json", b"{}", "text/html"))
        self.assertFalse(api.authentic_document("json", b"0", "application/json"))
        self.assertFalse(api.authentic_document("json", b"x" * (api.MAX_BYTES + 1), "application/json"))

    def test_only_documented_fixed_tls_host_is_contacted(self):
        calls, hosts = [], []
        def resolver(host):
            hosts.append(host)
            return ["8.8.8.8"]
        def factory(host, ip):
            self.assertEqual((host, ip), (api.HOST, "8.8.8.8"))
            return FakeConnection(Response(), calls)
        value = api.observe("directory", resolver=resolver, connection=factory)
        self.assertEqual(value["status"], "API_DOCUMENT_VISIBLE_ONLY")
        self.assertEqual(hosts, [api.HOST])
        self.assertEqual([x[1] for x in calls if x[0] == "GET"], ["/"])
        self.assertEqual(calls[-1], ("close",))
        self.assertNotIn("procurements", str(value).lower())

    def test_redirect_never_followed_and_http_200_challenge_rejected(self):
        calls = []
        def probe(response):
            return api.observe("sections",
                resolver=lambda _: ["8.8.8.8"],
                connection=lambda host, ip: FakeConnection(response, calls))
        self.assertEqual(probe(Response(status=301))["http_status"], 301)
        self.assertEqual(probe(Response(payload=b"<html>captcha</html>",
                                         mime="text/html"))["status"], "HTTP_200_NON_API_DOCUMENT")
        self.assertEqual([x[1] for x in calls if x[0] == "GET"],
                         ["/lists/sections", "/lists/sections"])

    def test_unapproved_label_never_does_dns_or_any_http(self):
        dns = []
        for raw in ("http://api.tektorg.ru/", "../", "api.tektorg.ru/procedures/wsdl", ""):
            with self.assertRaises(ValueError):
                api.observe(raw, resolver=lambda x: dns.append(x))
        self.assertEqual(dns, [])

    def test_no_client_data_or_native_tenders_claimed_in_diagnostics(self):
        from contextlib import redirect_stdout
        from io import StringIO
        with patch.object(api, "observe", return_value={"status": "API_DOCUMENT_VISIBLE_ONLY"}) as obs:
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(api.main(), 0)
        self.assertEqual(obs.call_count, 3)
        for marker in ("RU_TEK_VERIFIED_NATIVE_TENDER_DETAILS=0",
                       "RU_TEK_WORKER_SQL_ACCEPTED=NO",
                       "RU_TEK_CUSTOMER_NOTIFIED=NO",
                       "PRODUCTION_CHANGED=NO"):
            self.assertIn(marker, output.getvalue())

if __name__ == "__main__":
    unittest.main()
