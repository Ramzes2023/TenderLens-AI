"""Safety and source scope contracts for operator-only trusted RU diagnostics."""
import unittest
from unittest.mock import patch
from scripts.ru_trusted_live_probe import TARGETS, ON_DEMAND_TARGETS, UnsafeAddress, checked_ips, describe, main, read_public, Target

class ProbeSafetyTests(unittest.TestCase):
    def test_fixed_unique_approved_targets(self):
        self.assertEqual(len(TARGETS), 37)
        pairs = {(t.host, t.path) for t in TARGETS.values()}
        self.assertEqual(len(pairs), len(TARGETS))
        self.assertTrue(all(t.mode in {"html", "rss"} for t in TARGETS.values()))

    def test_fabrikant_legacy_alias_uses_real_published_register_not_obsolete_soap4(self):
        published = TARGETS["fabrikant_44_mirror"]
        self.assertEqual(published, Target("44.fabrikant.ru", "/44/catalog/procedure/published"))
        self.assertNotEqual(published.path, "/44/catalog/procedure/requestOffer")
        self.assertEqual(published.host, TARGETS["fabrikant_44"].host)
        self.assertNotEqual(published.path, TARGETS["fabrikant_44"].path)
        # Two operator choices on one official host are not independent feeds.
        self.assertEqual(sum(t.host == published.host for t in TARGETS.values()), 2)

    def test_caucasus_exact_public_targets_not_live_source_claims(self):
        self.assertEqual(TARGETS["ossetia_official_small"], Target("15.portalregion.ru", "/"))
        self.assertEqual(TARGETS["stavropol_rts_small"], Target("market26.rts-tender.ru", "/"))
        self.assertEqual(TARGETS["ossetia_official_small"].mode, "html")
        self.assertEqual(TARGETS["stavropol_rts_small"].mode, "html")

    def test_unapproved_choice_never_resolves_dns(self):
        with patch("scripts.ru_trusted_live_probe.socket.getaddrinfo") as dns:
            self.assertEqual(main("https://evil.invalid/"), 2)
            self.assertEqual(main(".."), 2)
            self.assertEqual(main(""), 2)
            dns.assert_not_called()

    def test_private_dns_never_connects(self):
        fixture = [(2,1,6,"",("127.0.0.1",443))]
        with patch("scripts.ru_trusted_live_probe.socket.getaddrinfo", return_value=fixture):
            with self.assertRaises(UnsafeAddress):
                checked_ips("allowed.example")
        mixed = [(2,1,6,"",("8.8.8.8",443)), (2,1,6,"",("192.168.1.1",443))]
        with patch("scripts.ru_trusted_live_probe.socket.getaddrinfo", return_value=mixed):
            with self.assertRaises(UnsafeAddress):
                checked_ips("allowed.example")

    def test_public_dns_accepted_not_contacted(self):
        x = [(2,1,6,"",("8.8.8.8",443)), (2,1,6,"",("1.1.1.1",443))]
        with patch("scripts.ru_trusted_live_probe.socket.getaddrinfo", return_value=x):
            self.assertEqual(checked_ips("safe.example"), ["1.1.1.1","8.8.8.8"])

    def test_unapproved_redirect_like_and_query_rejected_before_dns(self):
        with patch("scripts.ru_trusted_live_probe.checked_ips") as dns:
            for path in ["//evil/path","/path?next=http://evil","/p#frag","/slash\\evil","example"]:
                with self.assertRaises(ValueError):
                    read_public(Target("good.example",path))
            dns.assert_not_called()

    def test_bounded_html_and_rss_classification(self):
        self.assertEqual(describe("rss",b"<rss><channel><item/><item/></channel></rss>")["rss_items"],2)
        self.assertEqual(describe("html",b'<a href="/t/123">test</a>')["anchor_tokens"],1)
        with self.assertRaises(Exception):
            describe("rss",b"not rss")


    def test_batch_enforces_real_reachability_and_never_marks_ingestion(self):
        from io import StringIO
        from contextlib import redirect_stdout
        with patch("scripts.ru_trusted_live_probe.read_public", return_value=("text/html", b"<a href='/proc/123'>test</a>")) as fn:
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main("batch_priority"), 0)
            self.assertEqual(fn.call_count, 37)
            self.assertIn("RU_BATCH_HTTPS_VISIBLE=37/37", output.getvalue())
            self.assertIn("RU_BATCH_NOTICE_DETAIL_VERIFIED=NO", output.getvalue())
        def blocked(target):
            if target.host == "44.fabrikant.ru":
                raise TimeoutError("no official response")
            return ("text/html", b"<a href='/proc/123'>test</a>")
        with patch("scripts.ru_trusted_live_probe.read_public", side_effect=blocked):
            with redirect_stdout(StringIO()):
                self.assertEqual(main("batch_priority"), 2)

    def test_every_batch_target_has_safe_fixed_origin_and_path(self):
        from urllib.parse import urlsplit
        self.assertEqual(len({(t.host,t.path) for t in TARGETS.values()}),37)
        for item in TARGETS.values():
            url = urlsplit("https://" + item.host + item.path)
            self.assertEqual(url.hostname, item.host)
            self.assertEqual(url.scheme, "https")
            self.assertFalse(url.username or url.password or url.query or url.fragment)

if __name__ == "__main__":
    unittest.main()
