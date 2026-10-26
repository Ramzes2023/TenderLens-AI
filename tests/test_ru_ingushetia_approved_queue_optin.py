"""Separate Ingushetia opt-in queue safety; main approved RU queue remains unchanged."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import JobRepository, JobService
from app.jobs.models import JobScope
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.ru_cycle import RU_APPROVED_SOURCES, INGUSHETIA_APPROVED_SOURCES, approved_ru_keys, enqueue_approved_ru
from app.sources.ingestion import ConnectorSyncService, SYSTEM_SCOPE


def catalog(**flags):
    base = MonitoringSettings(False, 600, 20, 5, 12, (), None)
    return build_source_catalog(replace(base, **flags))


def queue(tmp_path, cat):
    db = Database(DatabaseSettings("", tmp_path / "ingushetia-approved.sqlite"))
    repo = JobRepository(db)
    repo.initialize()
    return db, repo, ConnectorSyncService(JobService(repo), cat)


def test_main_nine_approved_sources_are_not_reordered_or_removed():
    assert RU_APPROVED_SOURCES[-2:] == ("ru_samara_public_list", "ru_dagestan_public_list")
    assert INGUSHETIA_APPROVED_SOURCES == (
        "ru_ingushetia_eis44", "ru_ingushetia_fabrikant44"
    )


def test_ingushetia_pair_stays_default_off_and_only_explicit_opt_in_is_queued(tmp_path):
    from app.sources.ru_notice_identity import original_notice_key
    from app.sources.models import TenderNotice

    disabled = catalog()
    assert "ru_ingushetia_eis44" not in disabled.enabled_keys
    assert "ru_ingushetia_fabrikant44" not in disabled.enabled_keys
    with pytest.raises(ValueError, match="No operator-approved"):
        approved_ru_keys(disabled)

    cat = catalog(ru_ingushetia_eis44_enabled=True,
                  ru_ingushetia_fabrikant44_enabled=True)
    assert approved_ru_keys(cat) == ("ru_ingushetia_eis44", "ru_ingushetia_fabrikant44")
    db, jobs, service = queue(tmp_path, cat)
    try:
        start = datetime(2026, 10, 20, 11, 15, tzinfo=timezone.utc)
        first = enqueue_approved_ru(service, cat, now=start)
        again = enqueue_approved_ru(service, cat, now=start + timedelta(minutes=31))
        assert tuple(first) == ("ru_ingushetia_eis44", "ru_ingushetia_fabrikant44")
        assert {key: job["job_id"] for key, job in first.items()} == {
            key: job["job_id"] for key, job in again.items()
        }
        assert {jobs.get(data["job_id"], scope=SYSTEM_SCOPE).payload["source_id"]
                for data in first.values()} == set(first)
        with db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM durable_jobs").fetchone()[0] == 2
    finally:
        db.close()

    number = "0114500000826002402"
    originals = [
        TenderNotice(source="ru_ingushetia_eis44", external_id=number,
                     tender_number=number, title="Ремонт улицы",
                     url="https://zakupki.gov.ru/epz/order/notice/ok20/view/common-info.html?regNumber=" + number),
        TenderNotice(source="ru_ingushetia_fabrikant44", external_id=number,
                     tender_number=number, title="Ремонт улицы",
                     url="https://44.fabrikant.ru/44/procedure/okb20/" + number),
    ]
    assert original_notice_key(originals[0]) == original_notice_key(originals[1]) == (
        "eis_44", number,
    )


def test_main_samara_config_is_preserved_without_enabling_ingushetia(monkeypatch, tmp_path):
    """Merge-safety: main's separate regional opt-in survives this draft branch."""
    from app.monitoring.config import load_monitoring_settings, MonitoringConfigurationError

    config_file = tmp_path / "missing.env"
    monkeypatch.delenv("RU_SAMARA_PUBLIC_LIST_ENABLED", raising=False)
    baseline = load_monitoring_settings(config_file)
    assert baseline.ru_samara_public_list_enabled is False
    assert baseline.ru_ingushetia_eis44_enabled is False
    assert baseline.ru_ingushetia_fabrikant44_enabled is False

    monkeypatch.setenv("RU_SAMARA_PUBLIC_LIST_ENABLED", "true")
    selected = load_monitoring_settings(config_file)
    assert selected.ru_samara_public_list_enabled is True
    assert selected.ru_ingushetia_eis44_enabled is False
    assert selected.ru_ingushetia_fabrikant44_enabled is False

    monkeypatch.setenv("RU_SAMARA_PUBLIC_LIST_ENABLED", "unsafe")
    with pytest.raises(MonitoringConfigurationError):
        load_monitoring_settings(config_file)
