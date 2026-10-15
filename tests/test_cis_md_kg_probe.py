"""Fully offline safety and parsing contracts for public CIS source probe."""
import io
import json
import unittest
from urllib.error import URLError

from scripts.cis_md_kg_public_probe import (
    MAX_BODY, check_url, describe_payload, probe,
)


class Reply:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, data):
        self._data = io.BytesIO(data)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._data.close()

    def read(self, n=-1):
        return self._data.read(n)


class Opener:
    def __init__(self, data=None, failure=None):
        self.data, self.failure, self.calls = data, failure, []

    def open(self, request, timeout):
        self.calls.append((request.full_url, timeout))
        if self.failure:
            raise self.failure
        return Reply(self.data)


class PublicProbeTests(unittest.TestCase):
    def test_https_explicit_allowlist(self):
        for url in [
            "http://public.mtender.gov.md/tenders/",
            "https://public.mtender.gov.md.evil.example/tenders/",
            "https://user@zakupki.gov.kg/popp/",
            "https://zakupki.gov.kg:444/popp/",
            "https://zakupki.gov.kg/popp/#section",
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                check_url(url)
        check_url("https://public.mtender.gov.md/tenders/")
        check_url("https://zakupki.gov.kg/popp/")

    def test_moldova_ocids_not_confused_with_full_tenders(self):
        rows = {"offset": "", "data": [
            {"ocid": "ocds-b3wdp1-MD-1770204825070", "date": "2026-10-01T00:00:00Z"},
            {"ocid": "https://evil.example/path"},
        ]}
        out = describe_payload("md_mtender_index", json.dumps(rows).encode(), "application/json")
        self.assertEqual(out["ocid_count"], 1)
        self.assertTrue(out["verified"])
        self.assertEqual(out["kind"], "public_ocid_listing")
        detail = describe_payload("md_mtender_known_detail", json.dumps(rows).encode(), "application/json")
        self.assertFalse(detail["verified"])

    def test_oсds_detail_requires_title(self):
        doc = {"releases": [{"tender": {"title": "Achiziția medicamentelor"}}]}
        out = describe_payload("md_mtender_known_detail", json.dumps(doc).encode(), "application/json")
        self.assertTrue(out["verified"])
        self.assertEqual(out["records_with_title"], 1)
        compiled = {"records": [{"compiledRelease": {"tender": {"title": "Servicii medicale"}}}]}
        self.assertTrue(describe_payload("md_mtender_known_detail", json.dumps(compiled).encode(), "application/json")["verified"])
        self.assertTrue(describe_payload("md_alternative_index", json.dumps({"data": [{"ocid": "ocds-b3wdp1-MD-1770204825070"}]}).encode(), "application/json")["verified"])
        self.assertFalse(describe_payload("md_mtender_known_detail", b"<html></html>", "text/html")["verified"])

    def test_kg_listing_needs_actual_tender_links(self):
        content = b'<a href="view/order/view.xhtml?id=561794973">Tender</a>'
        self.assertTrue(describe_payload("kg_portal_home", content, "text/html")["verified"])
        self.assertFalse(describe_payload("kg_portal_home", b"<html>JSF form</html>", "text/html")["verified"])
        self.assertFalse(describe_payload("kg_known_detail", b"<html>Only navigation</html>", "text/html")["verified"])

    def test_kyrgyzstan_new_portal_requires_real_ids_and_context(self):
        listing = "№202610122560014988 Жарыяланган Товары Организация Жалал-Абад Планируемая сумма 18000 сом"
        result = describe_payload("kg_new_portal", listing.encode("utf-8"), "text/html")
        self.assertTrue(result["verified"])
        self.assertEqual(result["order_ids"], 1)
        self.assertFalse(describe_payload("kg_new_portal", b"<html>menu only</html>", "text/html")["verified"])
        self.assertFalse(describe_payload("kg_new_portal", b"202610122560014988", "text/html")["verified"])

    def test_official_moldova_agency_index_not_empty_page(self):
        document = ('<table><tr><td>AP LP MTender</td>'
                    '<td>ocds-b3wdp1-MD-1780470314481</td>'
                    '<td>Lucrări de reabilitare</td></tr></table>')
        out = describe_payload("md_agency_listing", document.encode(), "text/html")
        self.assertTrue(out["verified"])
        self.assertEqual(out["ocid_count"], 1)
        self.assertFalse(describe_payload("md_agency_listing", b"<table>No notices</table>", "text/html")["verified"])

    def test_probe_is_bounded_and_has_no_fallback(self):
        opener = Opener(json.dumps({"data": [{"ocid": "ocds-b3wdp1-MD-1770204825070"}]}).encode())
        result = probe("md_mtender_index", "https://public.mtender.gov.md/tenders/", opener)
        self.assertTrue(result["verified"])
        self.assertEqual(len(opener.calls), 1)
        self.assertLessEqual(opener.calls[0][1], 12)
        oversized = Opener(b" " * (MAX_BODY + 1))
        self.assertEqual(probe("kg_portal_home", "https://zakupki.gov.kg/popp/", oversized)["reason"],
                         "response_over_limit")
        blocked = Opener(failure=URLError("unreachable"))
        status = probe("md_mtender_index", "https://public.mtender.gov.md/tenders/", blocked)
        self.assertFalse(status["reachable"])
        self.assertEqual(status["reason"], "network_or_tls_error")


if __name__ == "__main__":
    unittest.main()
