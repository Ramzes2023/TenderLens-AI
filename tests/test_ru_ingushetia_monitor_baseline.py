"""Operator-only /monitor_on baseline: no pre-existing regional SQL alerts.

Offline fixtures, disposable databases, no Telegram Bot API or live source.
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.bot.monitoring import monitor_on_handler
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.monitoring.config import MonitoringSettings
from app.monitoring.repository import MonitoringRepository
from app.monitoring.service import TenderMonitorService
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import connector_version
from app.sources.models import TenderNotice
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import (
    FreshIngushetiaWorkerSource, fresh_ingushetia_worker_catalog,
)

SOURCE = "ru_ingushetia_eis44"


def settings(**updates):
    base = dict(
        enabled=True, interval_seconds=600, max_items=2,
        max_notifications_per_cycle=2, request_timeout=15,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        ru_background_catalog_enabled=True,
        ru_ingushetia_eis44_enabled=True,
        ru_ingushetia_fabrikant44_enabled=False,
        ru_ingushetia_worker_sql_alerts_enabled=True,
    )
    base.update(updates)
    return MonitoringSettings(**base)


def notice(index):
    number = f"011450000082600{index:04d}"
    return TenderNotice(
        source=SOURCE, external_id=number, tender_number=number,
        title="Поставка медицинского оборудования",
        customer="Комитет государственного заказа Республики Ингушетия",
        region="Республика Ингушетия",
        url="https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=" + number,
    )


class Message:
    from_user = SimpleNamespace(id=101)
    chat = SimpleNamespace(id=5001)

    def __init__(self):
        self.messages = []
        self.edits = []

    async def answer(self, text, **kwargs):
        self.messages.append(text)
        return self

    async def edit_text(self, text):
        self.edits.append(text)


def test_subscribe_marks_every_recent_regional_original_not_only_first_page(tmp_path):
    db = Database(DatabaseSettings("ing-baseline", tmp_path / "sources.sqlite"))
    repo = OpportunityRepository(db)
    repo.initialize()
    monitor_repo = MonitoringRepository(tmp_path / "monitor.sqlite")
    monitor_repo.initialize()
    cfg = settings()
    cat = fresh_ingushetia_worker_catalog(build_source_catalog(cfg), repo)
    service = TenderMonitorService(cfg, None, monitor_repo, None)

    numbers = [notice(i).tender_number for i in range(150, 184)]
    try:
        for index in range(150, 184):
            repo.upsert(notice(index), connector_version(SOURCE))
        msg = Message()
        asyncio.run(monitor_on_handler(msg, service, cat))
        assert len(msg.edits) == 1
        assert "34" in msg.edits[0]
        assert "включён" in msg.edits[0]
        assert monitor_repo.get_subscription(101).enabled is True
        assert all(monitor_repo.seen(101, "eis_44", number) for number in numbers)
        # 34 already-visible notices cannot be reinterpreted as new on the
        # next notification cycle merely because max_items was only 2.
        matches, report = asyncio.run(service.fetch_matches_from_catalog(
            cat, 101, source_keys=(SOURCE,),
        ))
        assert not report.total_failure
        assert asyncio.run(service.unseen_matches(101, matches)) == []
        assert len(msg.messages) == 1  # Status text, NOT 34 Telegram tenders
    finally:
        db.close()


def test_subscribe_rejects_unbounded_or_unverified_regional_baseline(monkeypatch, tmp_path):
    db = Database(DatabaseSettings("ing-baseline-bound", tmp_path / "sources.sqlite"))
    repo = OpportunityRepository(db)
    repo.initialize()
    monitor_repo = MonitoringRepository(tmp_path / "monitor.sqlite")
    monitor_repo.initialize()
    cfg = settings()
    cat = fresh_ingushetia_worker_catalog(build_source_catalog(cfg), repo)
    service = TenderMonitorService(cfg, None, monitor_repo, None)
    try:
        async def oversized(self, limit=20):
            assert limit == 1000
            return [notice(150)] * 1000
        monkeypatch.setattr(FreshIngushetiaWorkerSource, "fetch", oversized)
        msg = Message()
        asyncio.run(monitor_on_handler(msg, service, cat))
        assert len(msg.edits) == 1
        assert "Не удалось включить мониторинг" in msg.edits[0]
        assert monitor_repo.get_subscription(101) is None
        assert not monitor_repo.seen(101, "eis_44", notice(150).tender_number)
    finally:
        db.close()


def test_subscribe_cannot_fall_back_to_live_network_catalog(tmp_path):
    cfg = settings()
    live = build_source_catalog(cfg)
    repository = MonitoringRepository(tmp_path / "monitor.sqlite")
    repository.initialize()
    service = TenderMonitorService(cfg, None, repository, None)
    msg = Message()
    asyncio.run(monitor_on_handler(msg, service, live))
    assert "Не удалось включить мониторинг" in msg.edits[0]
    assert repository.get_subscription(101) is None
