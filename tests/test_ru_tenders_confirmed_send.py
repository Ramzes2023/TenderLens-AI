"""Manual /tenders must never lose genuine notices before Telegram confirms send.

All notices here are synthetic OFFLINE fixtures; test does not assert live
source access or production Telegram delivery.
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.bot.monitoring import tenders_handler
from app.monitoring.service import MonitorMatch
from app.sources.models import TenderNotice


def notice(n):
    return MonitorMatch(TenderNotice(
        source="ru_samara_public_list",
        external_id=str(n),
        tender_number=f"ИМЗ-2026-{n:06d}",
        title=f"Поставка оборудования номер {n}",
        url="https://webtorgi.samregion.ru/smallpurchases/GzwSP/NoticesGrid",
        customer="Самарская муниципальная школа",
        region="Самарская область",
    ), ("оборудование",))


class FakeMessage:
    from_user = SimpleNamespace(id=777)
    chat = SimpleNamespace(id=888)

    def __init__(self, *, fail_on_nth_tender=0):
        self.sent = []
        self.fail_on_nth_tender = fail_on_nth_tender
        self.tenders_attempted = 0

    async def answer(self, text, **kwargs):
        if text.startswith("1. 📌") or text.startswith("2. 📌"):
            self.tenders_attempted += 1
            if self.tenders_attempted == self.fail_on_nth_tender:
                raise OSError("Synthetic Telegram send failed")
        self.sent.append((text, kwargs))
        return SimpleNamespace(edit_text=self.edit_text,
                               message_id=len(self.sent), chat=self.chat)

    async def edit_text(self, text):
        self.sent.append((text, {}))


class FakeService:
    settings = SimpleNamespace(max_notifications_per_cycle=1)

    def __init__(self):
        self.records = [notice(1), notice(2)]
        self.claimed = []
        self.fetched = 0
        self.legacy_fetched = 0

    async def fetch_matches_from_catalog(self, catalog, owner):
        assert owner == 777
        self.fetched += 1
        return self.records, SimpleNamespace(
            attempted_sources=("ru_samara_public_list",),
            successful_sources=("ru_samara_public_list",),
            total_failure=False, failures=(),
        )

    async def fetch_matches(self, owner):
        assert owner == 777
        self.legacy_fetched += 1
        return self.records

    async def unseen_matches(self, owner, matches):
        assert owner == 777
        return [m for m in matches if m.notice.external_id not in self.claimed]

    async def claim_new(self, owner, matches):
        assert owner == 777
        self.claimed.extend(m.notice.external_id for m in matches)
        return matches

    async def scan_new(self, owner):
        raise AssertionError("Pre-send destructive scan must never run")

    async def scan_new_from_catalog(self, catalog, owner):
        raise AssertionError("Pre-send destructive catalog scan must never run")


def test_tenders_mark_only_successfully_delivered_messages_and_not_undelivered_limit():
    async def run():
        service, msg = FakeService(), FakeMessage()
        await tenders_handler(msg, monitoring_service=service, source_catalog=object())
        assert service.claimed == ["1"]
        assert service.fetched == 1
        assert any("не отправлены" in txt and "повторите /tenders" in txt
                   for txt, _ in msg.sent)
        assert any("Цена: не указана источником" in txt for txt, _ in msg.sent)
        followup = FakeMessage()
        await tenders_handler(followup, monitoring_service=service, source_catalog=object())
        assert service.claimed == ["1", "2"]
        assert not any("1. 📌 Поставка оборудования номер 1" in txt for txt, _ in followup.sent)
    asyncio.run(run())


def test_failing_real_send_keeps_same_notice_retryable():
    async def run():
        service, msg = FakeService(), FakeMessage(fail_on_nth_tender=1)
        with pytest.raises(OSError, match="Synthetic Telegram"):
            await tenders_handler(msg, monitoring_service=service, source_catalog=object())
        assert service.claimed == []
        retry = FakeMessage()
        await tenders_handler(retry, monitoring_service=service, source_catalog=object())
        assert service.claimed == ["1"]
        assert any("Номер: ИМЗ-2026-000001" in text for text, _ in retry.sent)
    asyncio.run(run())


def test_legacy_manual_tenders_also_wait_for_send_ack():
    async def run():
        service, msg = FakeService(), FakeMessage(fail_on_nth_tender=1)
        with pytest.raises(OSError):
            await tenders_handler(msg, monitoring_service=service)
        assert service.legacy_fetched == 1 and service.claimed == []
        await tenders_handler(FakeMessage(), monitoring_service=service)
        assert service.claimed == ["1"]
    asyncio.run(run())


@pytest.mark.parametrize("receipt", [
    None,
    SimpleNamespace(message_id=0, chat=SimpleNamespace(id=888)),
    SimpleNamespace(message_id=55, chat=SimpleNamespace(id=999)),
])
def test_manual_tenders_bad_telegram_receipt_keeps_original_for_retry(receipt):
    class UnconfirmedMessage(FakeMessage):
        async def answer(self, text, **kwargs):
            if text.startswith("1. 📌"):
                self.tenders_attempted += 1
                return receipt
            return await super().answer(text, **kwargs)

    async def run():
        service = FakeService()
        with pytest.raises(ValueError, match="acknowledgement invalid"):
            await tenders_handler(UnconfirmedMessage(), monitoring_service=service)
        assert service.claimed == []
        retry = FakeMessage()
        await tenders_handler(retry, monitoring_service=service)
        assert service.claimed == ["1"]
        assert any("Номер: ИМЗ-2026-000001" in text for text, _ in retry.sent)

    asyncio.run(run())
