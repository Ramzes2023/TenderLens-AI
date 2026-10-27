"""The hourly public-source scheduler must never become a general source poller."""
from datetime import datetime, timezone

import pytest

from app.sources.isolated_public_scheduler import next_utc_hour, approved_cycle
from app.api.isolated_public_sources import ISOLATED_SQLITE_URL


def test_scheduler_uses_next_real_utc_hour_not_arbitrary_interval():
    current=datetime(2026,10,27,18,59,59,tzinfo=timezone.utc)
    assert next_utc_hour(current)==datetime(2026,10,27,19,0,0,tzinfo=timezone.utc)
    assert next_utc_hour(datetime(2026,10,27,19,0,tzinfo=timezone.utc))==datetime(2026,10,27,20,0,tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        next_utc_hour(datetime(2026,10,27,18,0))


def test_scheduler_fail_closed_without_exact_isolated_env(monkeypatch):
    monkeypatch.delenv("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED",raising=False)
    monkeypatch.setenv("DATABASE_URL",ISOLATED_SQLITE_URL)
    monkeypatch.setenv("MIKROTON_TENDER_ENABLED","true")
    with pytest.raises(ValueError,match="not explicitly approved"):
        approved_cycle()
    monkeypatch.setenv("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED","true")
    monkeypatch.setenv("DATABASE_URL","sqlite:////app/data/tenderlens.db")
    with pytest.raises(ValueError,match="not explicitly approved"):
        approved_cycle()
    monkeypatch.setenv("DATABASE_URL",ISOLATED_SQLITE_URL)
    monkeypatch.setenv("MIKROTON_TENDER_ENABLED","false")
    with pytest.raises(ValueError,match="not explicitly approved"):
        approved_cycle()


def test_scheduler_has_no_host_access_and_is_opt_in():
    from pathlib import Path
    compose=Path("ops/public_sources/compose.yaml").read_text(encoding="utf-8")
    part=compose.split("\n  scheduler:",1)[1].split("\n  enqueue:",1)[0]
    assert 'profiles: ["verified-scheduler"]' in part
    assert "network_mode: none" in part
    assert "public_source_data:/app/data" in part
    assert "tenderlens-vps_tenderlens_data" not in part
    assert "TELEGRAM_BOT_TOKEN" not in part
    assert "ports:" not in part
