"""Ingushetia-only contracts against CURRENT main, without external network.

No fixture or synthetic row in this module may satisfy the real live gate.
"""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository
from app.jobs.models import JobScope
from app.jobs.worker import Worker
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import (
    HOSTS, JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService, connector_version,
)
from app.sources.models import TenderNotice
from app.sources.opportunities import OpportunityRepository
from app.sources.ru_cycle import approved_ru_keys
from app.sources.ru_ingushetia_eis44 import (
    IngushetiaEis44Source, normalize_ingushetia_notice, SOURCE_ID as EIS,
)
from app.sources.ru_ingushetia_fabrikant44 import (
    IngushetiaFabrikant44Source, SOURCE_ID as ETP, ORGANIZER, HOST,
    INN, extract_regional_listing, verified_fabrikant_notice, LIST_URL,
)
from app.sources.ru_notice_identity import original_notice_key


N = "0114500000826002402"
T = "Устройство ливневой канализации"
EIS_URL = ("https://zakupki.gov.ru/epz/order/notice/ok20/view/common-info.html"
           "?regNumber=" + N)
ETP_URL = "https://" + HOST + "/44/procedure/okb20/" + N


def settings(**kw):
    base = MonitoringSettings(False, 600, 10, 2, 20, (), None,
                              profile_feeds_enabled=False)
    return replace(base, **kw)


def eis_notice():
    return TenderNotice(
        source=EIS, external_id=N, tender_number=N, url=EIS_URL, title=T,
        customer=ORGANIZER, region="Республика Ингушетия",
    )


def etp_notice():
    return verified_fabrikant_notice(
        f"<html><h1>Сведения о закупке {N}</h1><main>"
        f"Наименование закупки {T} "
        f"Сведения об организаторе закупки {ORGANIZER} ИНН {INN}"
        "</main></html>".encode(), number=N, url=ETP_URL, title=T,
    )


def test_both_sources_are_individually_opt_in_and_registration_does_not_change_other_sources():
    baseline = build_source_catalog(settings())
    assert EIS not in baseline.enabled_keys and ETP not in baseline.enabled_keys
    assert HOSTS[EIS] == frozenset({"zakupki.gov.ru"})
    assert HOSTS[ETP] == frozenset({HOST, "soap4.fabrikant.ru"})
    a = build_source_catalog(settings(ru_ingushetia_eis44_enabled=True))
    b = build_source_catalog(settings(ru_ingushetia_fabrikant44_enabled=True))
    assert EIS in a.enabled_keys and ETP not in a.enabled_keys
    assert ETP in b.enabled_keys and EIS not in b.enabled_keys
    assert approved_ru_keys(a) == (EIS,)
    assert approved_ru_keys(b) == (ETP,)
    assert isinstance(a.registry.get(EIS).source, IngushetiaEis44Source)
    assert isinstance(b.registry.get(ETP).source, IngushetiaFabrikant44Source)
    assert a.registry.get(EIS).source.ca_bundle_file.is_file()
    assert set(baseline.enabled_keys) <= set(a.enabled_keys)


def test_eis_original_region_must_come_from_official_notice_fields_not_search_text():
    assert normalize_ingushetia_notice(eis_notice()).external_id == N
    assert normalize_ingushetia_notice(replace(
        eis_notice(), customer="Другой регион", region=None,
        title="Поставка в Республику Ингушетия",
    )) is None
    with pytest.raises(Exception):
        normalize_ingushetia_notice(replace(
            eis_notice(), url="https://evil.invalid/epz/order/notice/ok20/"
            "view/common-info.html?regNumber=" + N,
        ))


def test_fabrikant_requires_current_organizer_row_and_independent_original():
    html = (
        f'<table><tr><td>ОК</td><td><a href="/44/procedure/okb20/{N}">{N}</a></td>'
        f'<td>{T}</td><td>100 RUB</td><td>{ORGANIZER}</td><td>Заказчик</td></tr></table>'
    ).encode()
    assert extract_regional_listing(html) == [(N, ETP_URL, T)]
    assert "placer_search_str=" + INN in LIST_URL
    mirror = etp_notice()
    assert mirror.region == "Республика Ингушетия"
    assert mirror.tender_number == N
    with pytest.raises(ValueError):
        verified_fabrikant_notice(
            f"<h1>{N}</h1>{T} НЕВЕРНЫЙ ИНН 1234567890".encode(),
            number=N, url=ETP_URL, title=T,
        )


def test_original_identity_deduplicates_eis_and_accredited_etp():
    assert original_notice_key(eis_notice()) == original_notice_key(etp_notice()) == (
        "eis_44", N,
    )


def test_real_durable_worker_persists_verified_source_contract_without_external_http(tmp_path, monkeypatch):
    """Offline Worker contract only; separate strict live job must fetch upstream."""
    source = IngushetiaEis44Source()
    async def fixture_fetch(self, limit=20):
        assert 1 <= limit <= 100
        return [normalize_ingushetia_notice(eis_notice())]

    monkeypatch.setattr(IngushetiaEis44Source, "fetch", fixture_fetch)
    cat = build_source_catalog(settings(ru_ingushetia_eis44_enabled=True))
    db = Database(DatabaseSettings("ing-main-integration", tmp_path / "worker.sqlite"))
    try:
        jobs = JobRepository(db)
        jobs.initialize()
        store = OpportunityRepository(db)
        store.initialize()
        job = ConnectorSyncService(jobs, cat).enqueue(EIS)
        handler = HandlerRegistry()
        handler.register(JOB_TYPE, ConnectorSyncHandler(cat, store, max_records=3))
        assert Worker(jobs, handler, job_types=(JOB_TYPE,)).run_once()
        assert jobs.get(job.id, scope=JobScope()).state == "succeeded"
        rows = store.read(EIS, limit=5)
        assert [n.tender_number for n in rows] == [N]
        assert store.read(EIS, search_terms=(N,))[0].external_id == N
        assert store.upsert(rows[0], connector_version(EIS)) is False
    finally:
        db.close()


def test_safe_live_failure_reports_queue_status_without_urls_or_secrets():
    """Offline-only sanitized diagnostics; never count as live evidence."""
    from types import SimpleNamespace
    import json
    from scripts.ci_ru_ingushetia_main_live import (
        SafeWorkerFailure, safe_live_failure, SAFE_LIVE_ASSERTION_CODES,
    )

    pending = SafeWorkerFailure(SimpleNamespace(
        state="failed", failure_code="handler_error",
    ))
    detail = safe_live_failure(pending)
    assert detail == {
        "error_class": "BLOCKED", "stage": "WORKER_FAILED",
        "job_state": "failed", "job_failure_code": "handler_error",
    }
    unknown = SafeWorkerFailure(SimpleNamespace(
        state="https://private.invalid/path",
        failure_code="token=PRIVATE_BOT_TOKEN",
    ))
    output = json.dumps(safe_live_failure(unknown))
    assert "PRIVATE_BOT_TOKEN" not in output
    assert "private.invalid" not in output
    assert '"UNKNOWN"' in output

    for message, stage in SAFE_LIVE_ASSERTION_CODES.items():
        assert safe_live_failure(AssertionError(message))["stage"] == stage
    assert safe_live_failure(AssertionError("token=PRIVATE"))["stage"] == (
        "UNCLASSIFIED_ASSERTION"
    )
    assert "PRIVATE" not in json.dumps(
        safe_live_failure(AssertionError("token=PRIVATE"))
    )
