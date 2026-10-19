from tests.test_scoring_workers import system

"""Offline authorization contract for an explicit opt-in Samara source.

The input validation is NOT real upstream procurement proof; separate live
leased worker, SQL and signed-in API CI gates remain mandatory.
"""
import pytest

from app.monitoring.config import MonitoringSettings
from app.scoring.runs import SOURCE_IDS, ScoringInputError, validate_configuration
from app.sources.catalog import build_source_catalog


SOURCE = "ru_samara_public_list"


def catalog(*, enabled: bool):
    return build_source_catalog(MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=2,
        max_notifications_per_cycle=2, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        ru_samara_public_list_enabled=enabled,
    ))


def test_samara_is_a_valid_source_key_but_not_automatically_accessible():
    assert SOURCE in SOURCE_IDS
    assert validate_configuration((SOURCE,), 2)["sources"] == [SOURCE]
    assert SOURCE not in catalog(enabled=False).enabled_keys
    assert SOURCE in catalog(enabled=True).enabled_keys


def test_scoring_catalog_guard_uses_real_auth_workspace(system):
    # Fixture provides a real SQLite profile and job repository. No network.
    service = system.service
    service.catalog = None
    with pytest.raises(ScoringInputError):
        service.enqueue(scope=system.scope, sources=(SOURCE,), limit_per_source=2)

    service.catalog = catalog(enabled=False)
    with pytest.raises(ScoringInputError):
        service.enqueue(scope=system.scope, sources=(SOURCE,), limit_per_source=2)

    service.catalog = catalog(enabled=True)
    job = service.enqueue(scope=system.scope, sources=(SOURCE,), limit_per_source=2)
    assert job.state in {"queued", "succeeded"}
    assert job.payload["snapshot_id"]
