"""Safety and source scope contracts for operator-only trusted RU diagnostics."""
import unittest
from unittest.mock import patch
from scripts.ru_trusted_live_probe import TARGETS, ON_DEMAND_TARGETS, UnsafeAddress, checked_ips, describe, main, read_public, Target

class ProbeSafetyTests(unittest.TestCase):
    def test_roseltorg_exact_visible_original_links_are_only_unverified_candidates(self):
        from scripts.ru_trusted_live_probe import roseltorg_visible_original_candidates
        ident = "0318300120826000550"
        rt = "RT22042500009"
        html = (
            f"<head><title>hidden</title><a href='/procedure/{ident}/1'>hidden</a></head>"
            f"<template><a href='/procedure/{ident}/1'>hidden</a></template>"
            f"<script><a href='/procedure/{ident}/1'>hidden</a></script>"
            f"<body><a href='/procedure/{ident}/1'>first real listing link</a>"
            f"<a href='https://www.roseltorg.ru/procedure/{rt}'>second link</a>"
            f"<a href='/procedure/{ident}/1'>duplicate</a>"
            f"<a href='https://www.roseltorg.ru.evil.invalid/procedure/{ident}/1'>evil</a>"
            f"<a href='http://www.roseltorg.ru/procedure/{ident}/1'>insecure</a>"
            f"<a href='/procedure/{rt}?session=x'>unsafe query</a>"
            f"<a href='/procedure/{rt}%2f'>ambiguous escape</a>"
            f"<a href='/procedure/NOTACARD'>whitespace title</a>"
            "</body>"
        ).encode("utf-8")
        self.assertEqual(roseltorg_visible_original_candidates(html), 2)
        self.assertEqual(roseltorg_visible_original_candidates(
            f"<html><template><a href='/procedure/{ident}/1'>no visible</a></template>"
            "</html>".encode()), 0)
        with self.assertRaises(ValueError):
            roseltorg_visible_original_candidates(b"")

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


    def test_rss_rejects_nonfeed_dtd_and_xml_entity_without_false_visibility(self):
        for payload in (
            b"<html><body>login</body></html>",
            b"<errors><error>Not available</error></errors>",
            b'<!DOCTYPE rss [<!ENTITY leak "secret">]><rss><channel/></rss>',
            b'<rss><!DOCTYPE fake><channel/></rss>',
        ):
            with self.assertRaises(ValueError):
                describe("rss", payload)
        self.assertEqual(describe(
            "rss", b'<feed xmlns="http://www.w3.org/2005/Atom"><entry/></feed>'
        )["atom_items"], 1)

    def test_batch_enforces_real_reachability_and_never_marks_ingestion(self):
        from io import StringIO
        from contextlib import redirect_stdout
        def visible(target):
            if target.mode == "rss":
                return ("application/rss+xml", b"<rss><channel><item/></channel></rss>")
            return ("text/html", b"<a href='/proc/123'>test</a>")
        with patch("scripts.ru_trusted_live_probe.read_public", side_effect=visible) as fn:
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main("batch_priority"), 0)
            self.assertEqual(fn.call_count, 37)
            self.assertIn("RU_BATCH_HTTPS_VISIBLE=37/37", output.getvalue())
            self.assertIn("RU_BATCH_NOTICE_DETAIL_VERIFIED=NO", output.getvalue())
        def blocked(target):
            if target.host == "44.fabrikant.ru":
                raise TimeoutError("no official response")
            return visible(target)
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

    def test_five_operator_only_official_gpb_and_eis_targets_do_not_expand_batch(self):
        self.assertEqual(len(TARGETS), 37)
        self.assertEqual(ON_DEMAND_TARGETS, {
            "gpb_public_html": Target("etpgpb.ru", "/procedures/"),
            "gpb_new_public_html": Target("new.etpgpb.ru", "/procedures/"),
            "gpb_new_rss": Target("new.etpgpb.ru", "/procedures.rss", "rss"),
            "gpb_gos44_html": Target("gos.etpgpb.ru", "/44/catalog/procedure"),
            "eis_official_home": Target("zakupki.gov.ru", "/"),
        })
        self.assertFalse(set(TARGETS).intersection(ON_DEMAND_TARGETS))
        self.assertEqual(len({(z.host, z.path) for z in ON_DEMAND_TARGETS.values()}), 5)

    def test_gpb_official_only_choice_does_not_use_user_supplied_urls(self):
        from contextlib import redirect_stdout
        from io import StringIO
        with patch("scripts.ru_trusted_live_probe.read_public",
                   return_value=("text/html", b"<a href='/procedures/'>list</a>")) as reader:
            with redirect_stdout(StringIO()):
                self.assertEqual(main("gpb_public_html"), 0)
                self.assertEqual(main("gpb_new_public_html"), 0)
            self.assertEqual([x.args[0] for x in reader.call_args_list], [
                ON_DEMAND_TARGETS["gpb_public_html"],
                ON_DEMAND_TARGETS["gpb_new_public_html"],
            ])
        with patch("scripts.ru_trusted_live_probe.checked_ips") as dns:
            self.assertEqual(main("gpb_new_rss?ref=private"), 2)
            self.assertEqual(main("http://new.etpgpb.ru/procedures.rss"), 2)
            dns.assert_not_called()

    def test_main_only_selfhosted_gpbdetection_cannot_run_on_pr(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        text = (root / ".github/workflows/ru-trusted-operator-only.yml").read_text(encoding="utf-8")
        self.assertIn("on:\n  workflow_dispatch:\n", text)
        self.assertNotIn("  pull_request:", text)
        for label in ON_DEMAND_TARGETS:
            self.assertEqual(text.count("          - " + label + "\n"), 1)
        self.assertIn("if: github.ref == 'refs/heads/main'", text)
        self.assertIn("runs-on: [self-hosted, Linux, X64]", text)
        self.assertIn('test "$ACTUAL_RUNNER_NAME" = "VALYQON-RU-01"', text)
        self.assertIn("persist-credentials: false", text)

    def test_hosted_gpb_alternative_routes_are_observation_not_source_acceptance(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        raw = (root / ".github/workflows/ru-gpb-alternative-hosts-observation.yml").read_text(encoding="utf-8")
        self.assertIn("on:\n  pull_request:\n    branches: [main]", raw)
        self.assertIn("      - scripts/ru_trusted_live_probe.py", raw)
        self.assertIn("      - tests/test_ru_trusted_live_probe.py", raw)
        self.assertIn("    runs-on: ubuntu-latest", raw)
        self.assertNotIn("self-hosted", raw)
        self.assertIn("persist-credentials: false", raw)
        for key in (item for item in ON_DEMAND_TARGETS if item.startswith("gpb_")):
            self.assertIn(key, raw)
        # Separate main-only EIS observation never leaks into hosted GPB tests.
        self.assertNotIn("eis_official_home", raw)
        for marker in (
            "RU_GPB_DETAIL_VERIFIED=NO",
            "RU_GPB_WORKER_SQL_ACCEPTED=NO",
            "RU_GPB_TENANT_NOTIFIED=NO",
            "PRODUCTION_CHANGED=NO",
        ):
            self.assertIn(marker, raw)
        self.assertNotIn("curl -k", raw)
        self.assertNotIn("verify=False", raw)



    def test_five_current_blocked_publishers_are_fixed_observation_not_source_acceptance(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from scripts.ru_trusted_live_probe import RECOVERY_FIVE
        self.assertEqual(set(RECOVERY_FIVE), {
            "ingushetia", "chechnya", "roseltorg", "gpb", "tektorg"
        })
        self.assertEqual(RECOVERY_FIVE["gpb"], ON_DEMAND_TARGETS["gpb_public_html"])
        self.assertNotEqual(RECOVERY_FIVE["gpb"], TARGETS["gpb_rss"])
        self.assertEqual(RECOVERY_FIVE["ingushetia"], TARGETS["fabrikant_44_mirror"])
        self.assertEqual(RECOVERY_FIVE["chechnya"], ON_DEMAND_TARGETS["eis_official_home"])
        self.assertEqual(len({(v.host, v.path) for v in RECOVERY_FIVE.values()}), 5)

        def official_response(target):
            if target.mode == "rss":
                return "application/rss+xml", b"<rss><channel><item/></channel></rss>"
            return "text/html", b"<html><body>Official list</body></html>"

        with patch("scripts.ru_trusted_live_probe.read_public", side_effect=official_response) as call:
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main("priority_five_network"), 0)
            self.assertEqual(call.call_count, 5)
        for marker in (
            "RU_FIVE_FIRSTPARTY_HTTPS_VISIBLE=5/5",
            "RU_FIVE_ORIGINAL_DETAIL_VERIFIED=NO",
            "RU_FIVE_WORKER_SQL_ACCEPTED=NO",
            "RU_FIVE_REAL_TELEGRAM_ACK=NO",
            "PRODUCTION_CHANGED=NO",
        ):
            self.assertIn(marker, output.getvalue())
        self.assertNotIn("tender_count", output.getvalue().lower())

        def failed_source(target):
            if target == TARGETS["roseltorg"]:
                raise TimeoutError("External publisher unavailable")
            return official_response(target)
        with patch("scripts.ru_trusted_live_probe.read_public", side_effect=failed_source):
            with redirect_stdout(StringIO()):
                self.assertEqual(main("priority_five_network"), 2)

    def test_non200_firstparty_status_distinguished_from_network_failures(self):
        from scripts.ru_trusted_live_probe import Non200OfficialResponse
        from contextlib import redirect_stdout
        from io import StringIO
        self.assertEqual(Non200OfficialResponse(301).status, 301)
        self.assertEqual(Non200OfficialResponse(403).status, 403)
        for bad in (True, -1, 99, 600, "403"):
            with self.assertRaises(ValueError):
                Non200OfficialResponse(bad)

        def denied(target):
            if target == TARGETS["roseltorg"]:
                raise Non200OfficialResponse(403)
            if target.mode == "rss":
                return "application/rss+xml", b"<rss><channel/></rss>"
            return "text/html", b"<html>listing page</html>"

        with patch("scripts.ru_trusted_live_probe.read_public", side_effect=denied):
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main("priority_five_network"), 2)
        self.assertIn('"source": "roseltorg", "status": "HTTP_REACHABLE_NON200"', output.getvalue())
        self.assertIn('"http_status": 403', output.getvalue())
        self.assertNotIn('"url":', output.getvalue())
        self.assertIn("RU_FIVE_WORKER_SQL_ACCEPTED=NO", output.getvalue())

    def test_main_only_trusted_runner_exposes_fixed_five_source_choice(self):
        from pathlib import Path
        raw = (Path(__file__).resolve().parents[1] /
               ".github/workflows/ru-trusted-operator-only.yml").read_text(encoding="utf-8")
        self.assertIn("          - priority_five_network\n", raw)
        self.assertIn("          - eis_official_home\n", raw)
        self.assertIn("if: github.ref == 'refs/heads/main'", raw)
        self.assertIn("VALYQON-RU-01", raw)
        self.assertIn("persist-credentials: false", raw)
        self.assertNotIn("pull_request:", raw)



    def test_scoped_cert_pinned_russian_eis_tls_without_global_trust_mutation(self):
        import ssl
        from scripts.ru_trusted_live_probe import publisher_tls_context
        # The preinstalled repository EIS root is an immutable local file,
        # validated against the separately pinned canonical DER SHA-256.
        verified = publisher_tls_context("zakupki.gov.ru")
        self.assertTrue(verified.check_hostname)
        self.assertEqual(verified.verify_mode, ssl.CERT_REQUIRED)

        # Other official sites NEVER receive the EIS-specific CA.
        with patch("scripts.ru_eis_pinned_tls_probe.verify_root",
                   side_effect=AssertionError("should not load for another publisher")):
            for host in ("etpgpb.ru", "44.fabrikant.ru", "www.roseltorg.ru",
                         "www.tektorg.ru"):
                context = publisher_tls_context(host)
                self.assertTrue(context.check_hostname)
                self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

        # If the pinned EIS root fingerprint differs, reject before TLS
        # connection; do not silently trust an arbitrary local CA bundle.
        with patch("scripts.ru_eis_pinned_tls_probe.verify_root",
                   side_effect=ValueError("Root DER fingerprint mismatch")):
            with self.assertRaises(ValueError):
                publisher_tls_context("zakupki.gov.ru")


if __name__ == "__main__":
    unittest.main()
