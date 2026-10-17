"""Explicit activation only for independently verified MD and AZ sources.

Offline contracts are not acceptance of a live upstream feed or deployment.
"""
from dataclasses import replace
import os
import unittest
from unittest.mock import patch

from app.monitoring.config import MonitoringSettings, _bool
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import HOSTS, connector_version, validate_payload
from app.jobs.worker import PermanentJobError


def settings(**changes):
    base = MonitoringSettings(False, 600, 20, 5, 12, (), None)
    return replace(base, **changes)


class CISOptInActivationContracts(unittest.TestCase):
    def test_default_both_sources_are_inert(self):
        catalog = build_source_catalog(settings())
        for source in ("md_elicitatie", "az_azeristilik"):
            self.assertFalse(catalog.registry.get(source).enabled)
            self.assertNotIn(source, catalog.enabled_keys)
            with self.assertRaises(PermanentJobError):
                validate_payload(
                    {"schema": 1, "source_id": source,
                     "sync_window": "2026-10-18T12Z",
                     "connector_version": connector_version(source)},
                    catalog.registry,
                )

    def test_operator_flag_independently_enables_exact_source(self):
        for own, other, flag in (
            ("md_elicitatie", "az_azeristilik", "cis_md_elicitatie_enabled"),
            ("az_azeristilik", "md_elicitatie", "cis_az_azeristilik_enabled"),
        ):
            with self.subTest(source=own):
                catalog = build_source_catalog(settings(**{flag: True}))
                self.assertTrue(catalog.registry.get(own).enabled)
                self.assertFalse(catalog.registry.get(other).enabled)
                self.assertIn(own, catalog.enabled_keys)
                self.assertNotIn(other, catalog.enabled_keys)
                validate_payload(
                    {"schema": 1, "source_id": own,
                     "sync_window": "2026-10-18T12Z",
                     "connector_version": connector_version(own)},
                    catalog.registry,
                )

    def test_strict_pinned_real_hosts_and_no_credential_routes(self):
        self.assertEqual(HOSTS["md_elicitatie"], frozenset({"e-licitatie.md"}))
        self.assertEqual(HOSTS["az_azeristilik"], frozenset({"azeristilik.gov.az"}))

    def test_boolean_operator_inputs_fail_closed(self):
        for key in ("VALYQON_CIS_MD_ELICITATIE_ENABLED",
                    "VALYQON_CIS_AZ_AZERISTILIK_ENABLED"):
            with self.subTest(key=key):
                with patch.dict(os.environ, {key: "true"}):
                    self.assertTrue(_bool(key, False))
                with patch.dict(os.environ, {key: "false"}):
                    self.assertFalse(_bool(key, False))
                with patch.dict(os.environ, {key: "maybe"}):
                    with self.assertRaises(ValueError):
                        _bool(key, False)


if __name__ == "__main__":
    unittest.main()
