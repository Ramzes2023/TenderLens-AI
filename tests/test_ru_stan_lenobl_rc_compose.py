"""Offline security contract: isolated STAN+Lenobl RC never joins public/live Compose."""
from pathlib import Path
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/"ops/public_sources/compose.stan-lenobl-rc.yaml"

class RCComposeIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=FILE.read_text(encoding="utf-8")
        cls.manifest=yaml.safe_load(cls.raw)

    def test_separate_project_and_no_public_routes(self):
        m=self.manifest
        self.assertEqual(set(m["services"]),{"guest-sources","worker","enqueue"})
        self.assertEqual(set(m["volumes"]),{"stan_lenobl_rc_data"})
        self.assertNotIn("external",m["volumes"]["stan_lenobl_rc_data"] or {})
        self.assertEqual(set(m["networks"]),{"private_guest","publisher_outbound"})
        self.assertTrue(m["networks"]["private_guest"]["internal"])
        self.assertEqual(m["services"]["guest-sources"]["networks"],["private_guest"])
        self.assertEqual(m["services"]["worker"]["networks"],["publisher_outbound"])
        self.assertEqual(m["services"]["enqueue"]["network_mode"],"none")
        for service in m["services"].values():
            self.assertNotIn("ports",service)
            self.assertNotIn("network_mode",service) if service is not m["services"]["enqueue"] else None
            self.assertEqual(service["restart"],"no")
            self.assertTrue(service["read_only"])
            self.assertEqual(service["cap_drop"],["ALL"])
            self.assertIn("no-new-privileges:true",service["security_opt"])
            self.assertEqual(service["volumes"],["stan_lenobl_rc_data:/app/data"])
            self.assertEqual(service["image"],"valyqon-stan-lenobl-rc:reviewed")
        for forbidden in ("tenderlens-vps_edge","public_source_data:",
                          "tenderlens-vps_", "docker.sock",
                          "/var/run/docker.sock","network_mode: host","scheduler:"):
            self.assertNotIn(forbidden,self.raw)

    def test_same_safe_explicit_flags_and_offline_enqueuer(self):
        m=self.manifest
        env=m["x-rc-env"]
        for service in m["services"].values():
            self.assertEqual(service["environment"],env)
            self.assertEqual(service["tmpfs"],["/tmp:rw,nosuid,nodev,noexec,size=16m"])
        expected={
            "DATABASE_URL":"sqlite:////app/data/isolated-public-sources.sqlite3",
            "VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED":"true",
            "VALYQON_STAN_LENOBL_RC_MODE":"true",
            "STAN_COMMERCIAL_PUBLIC_ENABLED":"true",
            "LENOBL_SMALL_PUBLIC_ENABLED":"true",
            "VALYQON_CONNECTOR_MAX_RECORDS":"3",
            "MONITORING_ENABLED":"false",
            "VALYQON_EMAIL_MODE":"disabled",
            "TELEGRAM_BOT_TOKEN":"",
            "OUTBOUND_PROXY_URL":"",
            "VALYQON_RU_BACKGROUND_CATALOG_ENABLED":"false",
            "EIS_RSS_URLS":"",
            "MIKROTON_TENDER_ENABLED":"false",
            "VALYQON_PUBLIC_AI_ENABLED":"false"
        }
        for key,val in expected.items():
            self.assertEqual(str(env[key]),val,key)
        self.assertEqual(m["services"]["enqueue"]["profiles"],["manual-operator"])
        self.assertEqual(m["services"]["enqueue"]["command"],
                         ["python","-m","app.sources.enqueue","--source",
                          "stan_commercial_public"])
        self.assertIn("--connectors",m["services"]["worker"]["command"])
        self.assertEqual(m["services"]["guest-sources"]["healthcheck"]["test"][:3],
                         ["CMD","python","-c"])

if __name__=="__main__":
    unittest.main()
