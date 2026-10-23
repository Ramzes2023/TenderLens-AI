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

    def test_four_operator_only_official_gpb_targets_do_not_expand_batch(self):
        self.assertEqual(len(TARGETS), 37)
        self.assertEqual(ON_DEMAND_TARGETS, {
            "gpb_public_html": Target("etpgpb.ru", "/procedures/"),
            "gpb_new_public_html": Target("new.etpgpb.ru", "/procedures/"),
            "gpb_new_rss": Target("new.etpgpb.ru", "/procedures.rss", "rss"),
            "gpb_gos44_html": Target("gos.etpgpb.ru", "/44/catalog/procedure"),
        })
        self.assertFalse(set(TARGETS).intersection(ON_DEMAND_TARGETS))
        self.assertEqual(len({(z.host, z.path) for z in ON_DEMAND_TARGETS.values()}), 4)

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

    def test_primary_official_gpb_rss_gets_bounded_hosted_observation(self):
        # Publisher documents procedures.rss, not just /procedures/ HTML or
        # new.* redirects. Treat RSS reachability as observation, never as a
        # successful tender Worker or production source activation.
        from pathlib import Path
        self.assertEqual(TARGETS["gpb_rss"], Target("etpgpb.ru", "/procedures.rss", "rss"))
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/ru-gpb-alternative-hosts-observation.yml")
        raw = workflow.read_text(encoding="utf-8")
        self.assertIn(
            "for source in gpb_rss gpb_public_html gpb_new_public_html gpb_new_rss gpb_gos44_html; do",
            raw,
        )
        self.assertIn('python -B -m scripts.ru_trusted_live_probe "$source"', raw)
        self.assertIn("RU_GPB_DETAIL_VERIFIED=NO", raw)
        self.assertIn("RU_GPB_WORKER_SQL_ACCEPTED=NO", raw)
        self.assertIn("RU_GPB_TENANT_NOTIFIED=NO", raw)
        self.assertIn("PRODUCTION_CHANGED=NO", raw)
        self.assertNotIn("self-hosted", raw)

    def test_primary_gpb_rss_is_real_rss_not_login_html(self):
        self.assertEqual(
            describe("rss", b"<rss version='2.0'><channel><item/></channel></rss>"),
            {"rss_items": 1, "atom_items": 0},
        )
        with self.assertRaises(ValueError):
            describe("rss", b"<html><body>Login</body></html>")

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
        for key in ON_DEMAND_TARGETS:
            self.assertIn(key, raw)
        for marker in (
            "RU_GPB_DETAIL_VERIFIED=NO",
            "RU_GPB_WORKER_SQL_ACCEPTED=NO",
            "RU_GPB_TENANT_NOTIFIED=NO",
            "PRODUCTION_CHANGED=NO",
        ):
            self.assertIn(marker, raw)
        self.assertNotIn("curl -k", raw)
        self.assertNotIn("verify=False", raw)


if __name__ == "__main__":
    unittest.main()
