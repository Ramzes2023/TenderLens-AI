"""Offline security contract. Genuine upstream is checked in separate CI job."""
from pathlib import Path

def test_tektorg_live_acceptance_uses_production_leased_worker():
    text = Path("scripts/ci_ru_tektorg_real_worker.py").read_text(encoding="utf-8")
    assert "from scripts.ci_ru_leased_connector import run_leased_connector" in text
    assert "stats = run_leased_connector(db, catalog, store, SOURCE, max_records=5)" in text
    assert "SimpleNamespace" not in text
    assert "ConnectorSyncHandler(" not in text
    assert "TemporaryDirectory" in text
    assert "snapshot_catalog" in text
    assert "PRODUCTION_CHANGED=NO" in text
    assert "FAILURE_STAGE=LEASE_" in text
    assert "if code in {\"handler_error\", \"permanent_failure\", \"lease_expired\"," in text
    assert "print(str(e))" not in text
