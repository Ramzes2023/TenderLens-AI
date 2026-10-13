"""RU06 evidence audit and fail-closed routing; no HTTP or host temp dependency.

Excerpts are verbatim evidence, not positive adapter fixtures. There is no RU06
adapter: independent public notice contracts were not demonstrated by this batch.
"""
import hashlib
import json
from pathlib import Path

import pytest

from app.jobs.worker import PermanentJobError
from app.monitoring.config import MonitoringSettings
from app.scoring.runs import ScoringInputError, validate_configuration
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import HOSTS, connector_version, validate_payload
from app.sources.registry import SourceRegistry


FIXTURES = Path(__file__).parent / "fixtures" / "ru06"
AUDIT = json.loads((FIXTURES / "audit.json").read_text(encoding="utf-8"))
IDS = (
    "ru_eshoprzd", "ru_tender_pro", "ru_vologda", "ru_lenobl_store",
    "ru_spb_store", "ru_moscow_portal", "ru_mosreg_market", "ru_udmurt_small",
    "ru_tatar_small", "ru_dagestan_small", "ru_eurochem", "ru_polyus",
)


def test_complete_evidence_inventory_and_no_false_success():
    rows = AUDIT["candidates"]
    assert len(rows) == len(IDS) == 12
    assert {row["id"] for row in rows} == set(IDS)
    assert AUDIT["evidence_backed_adapters"] == 0
    assert AUDIT["independent_feeds_verified"] == 0
    assert all(not row["adapter_implemented"] for row in rows)
    assert all(not row["independent_feed_verified"] for row in rows)
    assert sum("excerpt_file" in row for row in rows) == 7
    assert sum(row["host_status"] == "BLOCKED" for row in rows) == 5
    assert {row["id"] for row in rows if row["classification"] ==
            "IMPLEMENTABLE_FROM_REAL_LISTING"} == {"ru_eurochem"}


@pytest.mark.parametrize("source_id", IDS)
def test_preserved_excerpt_integrity_or_exact_host_blocker(source_id):
    row = next(row for row in AUDIT["candidates"] if row["id"] == source_id)
    if "excerpt_file" not in row:
        assert row["host_reason"] in {"HTTP_503", "RemoteDisconnected", "URLError"}
        assert row["classification"] == "BLOCKED"
        assert "snapshot_sha256" not in row
        return
    raw = (FIXTURES / row["excerpt_file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == row["excerpt_sha256"]
    assert len(raw.decode("utf-8")) == row["excerpt_chars"]
    assert len(raw) < 10000
    assert len(row["snapshot_sha256"]) == 64
    assert row["snapshot_bytes"] >= len(raw)


def test_mirror_and_partial_records_are_not_independent_notice_fixtures():
    eurochem = (FIXTURES / "ru_eurochem.txt").read_text(encoding="utf-8")
    assert "ШТУЦЕРА, ХОМУТЫ" in eurochem
    assert "https://www.b2b-center.ru/app/market-next/shtutsera-khomuty/tender-4633901/" in eurochem
    assert "15.10.2026 07:00" in eurochem
    mosreg = (FIXTURES / "ru_mosreg_market.txt").read_text(encoding="utf-8")
    assert 'href="#"' in mosreg
    dagestan = (FIXTURES / "ru_dagestan_small.txt").read_text(encoding="utf-8")
    assert dagestan.startswith("var data = [")  # Inert text, never evaluated.
    assert dagestan.count("/portal/Show/contract?link=") == 5
    polyus = (FIXTURES / "ru_polyus.txt").read_text(encoding="utf-8")
    assert 'data-modal-data="0"' in polyus  # UI position is not a stable notice ID.
    assert "Поиск потенциальных поставщиков" in polyus


def test_candidates_have_no_catalog_registration_or_worker_host_grant(monkeypatch):
    monkeypatch.delenv("SAM_GOV_API_KEY", raising=False)
    monkeypatch.delenv("KZ_GOSZAKUP_API_TOKEN", raising=False)
    settings = MonitoringSettings(False, 600, 20, 5, 30, (), None,
                                  profile_feeds_enabled=False)
    catalog = build_source_catalog(settings)  # Builds objects only; no fetch.
    assert not set(IDS).intersection(catalog.registry.keys())
    assert not set(IDS).intersection(catalog.enabled_keys)
    assert not set(IDS).intersection(HOSTS)


@pytest.mark.parametrize("source_id", IDS)
def test_worker_and_scoring_reject_unimplemented_candidate(source_id):
    payload = {"schema": 1, "source_id": source_id,
               "sync_window": "2026-10-13T19Z",
               "connector_version": connector_version(source_id)}
    with pytest.raises(PermanentJobError):
        validate_payload(payload, SourceRegistry())
    with pytest.raises(ScoringInputError):
        validate_configuration([source_id], 20)
