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
        check_url("https://tender.gov.md/ro/documente-in-curs-de-examinare")
        check_url("https://mtender.gov.md/ru/tenders")
        check_url("https://goszakupki.okmot.kg/public/")

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

    def test_kyrgyzstan_new_portal_requires_complete_notice_fields(self):
        listing = (
            "<article>№202610122560014988 Жарыяланган Товары "
            "Приобретение умных электросчетчиков "
            "Организация Жалал-Абадский областной центр крови "
            "Планируемая сумма 18 000 Сом "
            "Дата публикации 12.10.2026 14:15 "
            "Дата окончания 15.10.2026 15:52</article>"
        )
        result = describe_payload("kg_new_portal", listing.encode("utf-8"), "text/html")
        self.assertTrue(result["verified"])
        self.assertEqual(result["order_ids"], 1)
        self.assertEqual(result["verified_order_count"], 1)
        self.assertEqual(describe_payload("kg_public_no_locale", listing.encode("utf-8"), "text/html")["verified_order_count"], 1)
        self.assertFalse(describe_payload("kg_new_portal", b"<html>menu only</html>", "text/html")["verified"])
        self.assertFalse(describe_payload("kg_new_portal", b"202610122560014988", "text/html")["verified"])
        self.assertFalse(describe_payload(
            "kg_new_portal", listing.replace("Дата окончания 15.10.2026 15:52", "").encode(), "text/html"
        )["verified"])
        self.assertFalse(describe_payload(
            "kg_new_portal", listing.replace("Планируемая сумма 18 000 Сом", "").encode(), "text/html"
        )["verified"])

    def test_kyrgyzstan_script_bundle_is_not_live_procurement_evidence(self):
        script = (
            '<script>window.__STATE__="№202610122560014988 Жарыяланган Товары '
            'Приобретение умных электросчетчиков Организация Жалал-Абадский центр '
            'Планируемая сумма 18 000 Сом Дата публикации 12.10.2026 14:15 '
            'Дата окончания 15.10.2026 15:52"</script>'
        )
        out = describe_payload("kg_new_portal", script.encode(), "text/html")
        self.assertEqual(out["order_ids"], 1)
        self.assertEqual(out["verified_order_count"], 0)
        self.assertFalse(out["verified"])

    def test_kyrgyzstan_does_not_borrow_another_notices_required_fields(self):
        html = (
            "<article>№202610122560014988 Жарыяланган Товары "
            "Incomplete first listing Организация First buyer</article>"
            "<article>№202610122562617004 Жарыяланган Услуги "
            "Приобретение услуг по ремонту компьютерной техники "
            "Организация Учреждение Войсковая часть 2031 "
            "Планируемая сумма 85 000 Сом "
            "Дата публикации 12.10.2026 14:28 "
            "Дата окончания 15.10.2026 15:26</article>"
        )
        out = describe_payload("kg_new_portal", html.encode(), "text/html")
        self.assertEqual(out["verified_order_count"], 1)
        self.assertTrue(out["verified"])

    def test_official_moldova_agency_requires_complete_tender_row(self):
        columns = [
            "1199821", "202632593", "03.09.2026", "",
            "Gimnaziul M Eminescu Telenesti", "LP MTender",
            "Procurarea produselor alimentare pentru semestrul 2 al anului 2026",
            "ocds-b3wdp1-MD-1783499242986", "15800000-6", "", "",
            "LP MTender",
        ]
        make_row = lambda parts: "<tr>" + "".join("<td>" + p + "</td>" for p in parts) + "</tr>"
        document = ("<table>" + make_row(columns) + "</table>").encode()
        for kind in ("md_agency_listing", "md_agency_ro_listing"):
            out = describe_payload(kind, document, "text/html")
            self.assertTrue(out["verified"])
            self.assertEqual(out["ocid_count"], 1)
            self.assertEqual(out["kind"], "official_agency_structured_ocid_rows")
            self.assertFalse(describe_payload(kind, b"<table>No notices</table>", "text/html")["verified"])
            for index, replacement in [
                (2, ""), (5, "Contract decision"), (6, ""), (7, "12345"), (8, ""),
            ]:
                changed = columns.copy()
                changed[index] = replacement
                self.assertFalse(
                    describe_payload(kind, make_row(changed).encode(), "text/html")["verified"],
                    (kind, index),
                )

    def test_moldova_agency_does_not_borrow_fields_between_rows(self):
        complete = [
            "1199821", "202632593", "03.09.2026", "",
            "Gimnaziul M Eminescu Telenesti", "LP MTender",
            "Procurarea produselor alimentare pentru semestrul 2 al anului 2026",
            "ocds-b3wdp1-MD-1783499242986", "15800000-6",
        ]
        missing_title = complete.copy()
        missing_title[6] = ""
        missing_date = complete.copy()
        missing_date[2] = ""
        html_rows = "".join(
            "<tr>" + "".join("<td>" + part + "</td>" for part in columns) + "</tr>"
            for columns in (missing_title, missing_date)
        )
        self.assertFalse(describe_payload(
            "md_agency_ro_listing", html_rows.encode(), "text/html")["verified"])

    def test_public_mtender_portal_only_counts_structured_ocids(self):
        data = b'<article>ocds-b3wdp1-MD-1787565971866 Public bulletin</article>'
        out = describe_payload("md_public_portal", data, "text/html")
        self.assertTrue(out["verified"])
        self.assertEqual(out["ocid_count"], 1)
        self.assertFalse(describe_payload("md_public_portal", b'<html>empty</html>', "text/html")["verified"])
        self.assertTrue(describe_payload("md_public_portal_ru", data, "text/html")["verified"])
        self.assertFalse(describe_payload("md_public_portal_ru", b"<html>empty</html>", "text/html")["verified"])

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
