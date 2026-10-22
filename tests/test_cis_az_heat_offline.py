"""Fail-closed parser contracts; offline fixtures never count as live tenders."""
import unittest

from scripts.ci_cis_az_heat_live_discovery import (
    SAMPLE, approved_post, detail_fields, extract_index,
)


def listing():
    slug = "is-yerlerinin-attestasiyasinin-kecirilmesi-xidmetinin-satinalinmasina-dair-kotirovka-sorgusu-elan-edir"
    return (
        '<html><script><a href="/post/not-a-valid-post-99999999">Fake tender</a></script>'
        f'<a href="/post/{slug}">İş yerlərinin attestasiyasının keçirilməsi xidmətinin satınalınmasına dair kotirovka sorğusu elan edir</a>'
        '<a href="/en/post/azeristiliktechizat-asc-komputer-ve-diger-ofis-avadanliqlarinin-satinalinmasina-dair-aciq-tender-elan-edir">'
        '"Azəristiliktəchizat" ASC kompüter avadanlıqlarının satınalınmasına dair tender elan edir</a>'
        '<a href="https://bad.example/post/fake-satinalinmasina-elan">External satınalınmasına</a></html>'
    ).encode()


def details(*, deadline="22.10.2026", buyer=True):
    return (f'<main><h1>İş yerlərinin attestasiyasının keçirilməsi xidmətinin satınalınmasına dair kotirovka sorğusu elan edir</h1>'
            + ('<p>Satınalan təşkilatın adı: "Azəristiliktəchizat" ASC</p>' if buyer else '<p>Other company</p>')
            + '<table><tr><td>Müsabiqənin başlanma tarixi və vaxtı:</td><td>07.10.2026</td></tr>'
            + f'<tr><td>Təkliflərin son təqdim olunma tarixi və vaxtı:</td><td>{deadline}</td></tr></table></main>').encode()


class AzerbaijanHeatOfflineContracts(unittest.TestCase):
    def test_index_only_visible_official_posts(self):
        urls = extract_index(listing())
        self.assertEqual(len(urls), 2)
        self.assertEqual(urls[0], SAMPLE)
        self.assertTrue(urls[1].startswith("https://azeristilik.gov.az/en/post/"))

    def test_invalid_url_forms_rejected(self):
        for value in (
            "http://azeristilik.gov.az/post/a-valid-looking-procurement-post",
            "https://evil.example/post/a-valid-looking-procurement-post",
            "https://azeristilik.gov.az/post/a-valid-looking-procurement-post?token=1",
            "https://azeristilik.gov.az@evil.example/post/a-valid-looking-procurement-post",
            "//evil.example/post/a-valid-looking-procurement-post",
            "/not-procurement/",
        ):
            with self.subTest(url=value):
                self.assertIsNone(approved_post(value))

    def test_strict_buyer_and_deadline(self):
        self.assertTrue(detail_fields(details())["verified"])
        self.assertFalse(detail_fields(details(buyer=False))["verified"])
        self.assertFalse(detail_fields(details(deadline="01.10.2026"))["verified"])
        self.assertFalse(detail_fields(details(deadline="22.19.2026"))["verified"])
        self.assertFalse(detail_fields(b"<html>Loading...</html>")["verified"])

    def test_script_content_and_size_do_not_count(self):
        self.assertEqual(extract_index(b"<script><a href='/post/legitimate-looking-tender'>Tender satin-alma</a></script>"), ())
        self.assertEqual(extract_index(b"X" * (768 * 1024 + 1)), ())
        self.assertFalse(detail_fields(("<p>Satınalan təşkilatın adı: Azəristiliktəchizat</p>" +
            "<script>Müsabiqənin başlanma tarixi və vaxtı: 07.10.2026 Təkliflərin son təqdim olunma tarixi və vaxtı: 22.10.2026</script>").encode("utf-8"))["verified"])


if __name__ == "__main__":
    unittest.main()


def test_bounded_discovery_keeps_only_fully_verified_first_party_detail(monkeypatch):
    """Offline resilience is never evidence for production activation."""
    from urllib.error import HTTPError, URLError
    import scripts.ci_cis_az_heat_live_discovery as mod

    first, second = extract_index(listing())
    third = "https://azeristilik.gov.az/post/official-published-procurement-card"
    fourth = "https://azeristilik.gov.az/post/another-expired-procurement-card"
    fifth = "https://azeristilik.gov.az/post/not-fetched-outside-budget"
    seen = []

    def scripted(url, opener):
        seen.append(url)
        if url == first:
            raise URLError(TimeoutError("network timeout"))
        if url == second:
            return details()
        if url == third:
            raise HTTPError(url, 404, "not found", None, None)
        if url == fourth:
            return b"<html>Loading...</html>"
        raise AssertionError("Exceeded detail budget")

    monkeypatch.setattr(mod, "fetch", scripted)
    report = mod.check_linked_details((first, second, third, fourth, fifth), object())
    assert report["checked_details"] == 4
    assert report["complete_details"] == 1
    assert report["detail_network_errors"] == {"TimeoutError": 1}
    assert report["detail_http_errors"] == {"404": 1}
    assert report["rejected_details"] == 1
    assert seen == [first, second, third, fourth]


def test_discovery_does_not_count_transport_errors_as_complete_details(monkeypatch):
    from urllib.error import URLError
    import scripts.ci_cis_az_heat_live_discovery as mod

    def unavailable(url, opener):
        raise URLError(ConnectionResetError("official unavailable"))

    monkeypatch.setattr(mod, "fetch", unavailable)
    report = mod.check_linked_details((SAMPLE, SAMPLE), object())
    assert report["complete_details"] == 0
    assert report["checked_details"] == 2
    assert report["detail_network_errors"] == {"ConnectionResetError": 2}
    assert not report["rejected_details"]
