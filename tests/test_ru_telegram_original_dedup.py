"""Real SQLite regression: a 44-FZ EIS/Fabrikant mirror generates one user alert.

Never dedup by keyword/title, never convert unproven marketplace identities,
and preserve already-delivered notices from existing source-local databases.
"""
import asyncio

from app.monitoring.config import MonitoringSettings
from app.monitoring.repository import MonitoringRepository
from app.monitoring.service import TenderMonitorService, MonitorMatch
from app.sources.models import TenderNotice


N = "0373100100726000010"


def item(source, number=N, original=None):
    return MonitorMatch(TenderNotice(
        source=source, external_id=number, tender_number=original or number,
        title="Поставка оборудования для муниципального учреждения",
        url="https://example.org/public/" + number,
    ), ("оборудование",))


def service(repo, scope_resolver=None):
    return TenderMonitorService(
        MonitoringSettings(False, 600, 20, 5, 12, (), None),
        None, repo, None, scope_resolver=scope_resolver,
    )


def test_fabrikant_and_eis_44_merge_only_by_valid_original_on_real_sqlite(tmp_path):
    repo = MonitoringRepository(tmp_path / "real.sqlite")
    repo.initialize()
    s = service(repo)

    async def check():
        entries = [item("eis"), item("fabrikant_44_public"), item("eis_44_html")]
        pending = await s.unseen_matches(91, entries)
        assert len(pending) == 1
        assert pending[0].notice.source == "eis"
        # Preview must be nonmutating until Telegram confirms delivery.
        assert not repo.seen(91, "eis_44", N)

        sent = await s.claim_new(91, pending)
        assert len(sent) == 1
        assert repo.seen(91, "eis_44", N)
        assert await s.unseen_matches(91, entries) == []
        assert await s.claim_new(91, entries) == []

    asyncio.run(check())


def test_already_delivered_legacy_eis_does_not_realert_as_fabrikant(tmp_path):
    repo = MonitoringRepository(tmp_path / "legacy.sqlite")
    repo.initialize()
    assert repo.mark_seen(12, "eis", N)
    s = service(repo)

    async def check():
        assert await s.unseen_matches(12, [item("fabrikant_44_public")]) == []
        assert await s.claim_new(12, [item("fabrikant_44_public")]) == []
        assert not repo.seen(12, "eis_44", N)

    asyncio.run(check())


def test_fabrikant_legacy_delivery_is_not_resent_as_eis(tmp_path):
    repo = MonitoringRepository(tmp_path / "legacy-fabrikant.sqlite")
    repo.initialize()
    assert repo.mark_seen(13, "fabrikant_44_public", N)
    s = service(repo)

    async def check():
        assert await s.unseen_matches(13, [item("eis"), item("eis_44_html")]) == []
        assert await s.claim_new(13, [item("eis")]) == []

    asyncio.run(check())


def test_legacy_surrogate_external_id_preserves_already_sent_notice(tmp_path):
    repo = MonitoringRepository(tmp_path / "legacy-surrogate.sqlite")
    repo.initialize()
    assert repo.mark_seen(9, "fabrikant_44_public", "local-surrogate-4")
    s = service(repo)
    old = item("fabrikant_44_public", "local-surrogate-4", N)

    async def check():
        assert await s.unseen_matches(9, [old]) == []
        assert await s.claim_new(9, [old]) == []
        assert not repo.seen(9, "eis_44", N)

    asyncio.run(check())


def test_no_guessing_marketplace_original_and_no_title_based_dedup(tmp_path):
    repo = MonitoringRepository(tmp_path / "distinct.sqlite")
    repo.initialize()
    s = service(repo)

    async def check():
        rows = [
            item("roseltorg_public", N),
            item("gpb_etp_public", N),
            item("fabrikant_44_public", N),
            item("eis", N),
        ]
        pending = await s.unseen_matches(17, rows)
        assert len(pending) == 3
        assert {n.notice.source for n in pending} == {
            "roseltorg_public", "gpb_etp_public", "fabrikant_44_public",
        }
        assert len(await s.claim_new(17, pending)) == 3
        assert await s.unseen_matches(17, rows) == []

    asyncio.run(check())


def test_company_scopes_and_users_remain_isolated(tmp_path):
    repo = MonitoringRepository(tmp_path / "scopes.sqlite")
    repo.initialize()
    current = {"value": "A"}
    s = service(repo, scope_resolver=lambda owner: current["value"])

    async def check():
        assert len(await s.claim_new(45, [item("eis"), item("fabrikant_44_public")])) == 1
        assert await s.unseen_matches(45, [item("fabrikant_44_public")]) == []
        current["value"] = "B"
        assert len(await s.unseen_matches(45, [item("eis")])) == 1
        assert len(await s.unseen_matches(46, [item("eis")])) == 1

    asyncio.run(check())


def test_other_223_originals_unified_but_non_eis_numbers_not_guessed(tmp_path):
    repo = MonitoringRepository(tmp_path / "223.sqlite")
    repo.initialize()
    s = service(repo)
    n223 = "32616478602"

    async def check():
        rows = [item("eis", n223), item("eis_223", n223)]
        assert len(await s.unseen_matches(22, rows)) == 1
        assert len(await s.claim_new(22, rows)) == 1
        assert repo.seen(22, "eis_223", n223)
        # A non-EIS 223-like ID on an independent platform is not EIS evidence.
        assert len(await s.unseen_matches(22, [item("stan_commercial_public", n223)])) == 1

    asyncio.run(check())
