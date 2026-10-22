"""Chechnya EIS adapter contracts. All inputs are synthetic; no live claim."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile

import pytest

from app.monitoring.config import (
    MonitoringConfigurationError,
    MonitoringSettings,
    load_monitoring_settings,
)
from app.sources.catalog import build_source_catalog
from app.sources.eis_rss import EisRssSource, SourceError, parse_eis_feed, verify_eis_feed_law
from app.sources.ingestion import HOSTS, connector_version, validate_payload
from app.sources.models import TenderNotice
from app.sources.ru_dedup import deduplicate
from app.sources.ru_notice_identity import original_notice_key
from app.sources.ru_chechnya_eis_rss import (
    SOURCE_KEY,
    ChechnyaEisRssSource,
    is_chechnya_notice,
    validate_chechnya_feed_urls,
)

URL = (
    "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html"
    "?fz44=on&searchString=%D0%A7%D0%B5%D1%87%D0%B5%D0%BD%D1%81%D0%BA%D0%B0%D1%8F%20%D0%A0%D0%B5%D1%81%D0%BF%D1%83%D0%B1%D0%BB%D0%B8%D0%BA%D0%B0"
)
EIS_ORIGINAL = (
    "https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html"
    "?regNumber=0194200000526005027"
)


def settings():
    return MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=20,
        max_notifications_per_cycle=5, request_timeout=20,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
    )


def notice(n, *, customer=None, region=None, title="Поставка продуктов питания"):
    return TenderNotice(
        source=SOURCE_KEY, external_id=str(n), title=title,
        url=EIS_ORIGINAL.replace("0194200000526005027", str(n)),
        tender_number=str(n), customer=customer, region=region,
    )


def test_adapter_disabled_by_default_and_worker_host_allowlisted():
    catalog = build_source_catalog(settings())
    assert SOURCE_KEY not in catalog.enabled_keys
    assert SOURCE_KEY not in {m.key for m in catalog.registry.metadata()}
    assert HOSTS[SOURCE_KEY] == frozenset({"zakupki.gov.ru"})


def test_operator_only_enable_registers_adapter_and_worker_routing():
    cfg = replace(settings(), ru_chechnya_eis_enabled=True,
                  ru_chechnya_eis_rss_urls=(URL,))
    catalog = build_source_catalog(cfg)
    assert SOURCE_KEY in catalog.enabled_keys
    entry = catalog.registry.get(SOURCE_KEY)
    assert isinstance(entry.source, ChechnyaEisRssSource)
    assert entry.official and entry.jurisdictions == ("RU",)
    payload = {
        "schema": 1, "source_id": SOURCE_KEY,
        "sync_window": "2026-10-22T11Z",
        "connector_version": connector_version(SOURCE_KEY),
    }
    assert validate_payload(payload, catalog.registry) is entry


@pytest.mark.parametrize("url", [
    "http://zakupki.gov.ru/epz/order/extendedsearch/rss.html?fz44=on&searchString=Чеченская",
    "https://evil.example/epz/order/extendedsearch/rss.html?fz44=on&searchString=Чеченская",
    "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?fz223=on&searchString=Чеченская",
    "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?fz44=on",
    "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?fz44=on&searchString=Москва",
])
def test_refuse_insecure_ambiguous_or_nationwide_feed(url):
    with pytest.raises((SourceError, ValueError)):
        validate_chechnya_feed_urls((url,))


def test_official_eis_rss_extensionless_alias_keeps_strict_host_and_region_gate():
    """Official RSS link can omit .html; no alternate host or arbitrary path."""
    exact_alias = URL.replace("/rss.html?", "/rss?")
    validate_chechnya_feed_urls((exact_alias,))
    with pytest.raises((SourceError, ValueError)):
        validate_chechnya_feed_urls((
            URL.replace("/rss.html?", "/rss/evil?"),
        ))
    with pytest.raises((SourceError, ValueError)):
        validate_chechnya_feed_urls((
            exact_alias.replace("zakupki.gov.ru", "evil.example"),
        ))


def test_extensionless_rss_does_not_relax_existing_national_eis_default():
    """Only Chechnya opts in; national direct EIS preserves .html-only gate."""
    from app.sources.eis_rss import validate_eis_direct_urls

    alias = URL.replace("/rss.html?", "/rss?")
    with pytest.raises(SourceError):
        validate_eis_direct_urls((alias,))
    validate_eis_direct_urls((alias,), allow_extensionless_rss=True)
    # The regular national adapter must still reject the alias in direct mode,
    # before any HTTP request or certificate override.
    async def check():
        with pytest.raises(SourceError):
            await EisRssSource((alias,), direct=True).fetch()
    asyncio.run(check())


def test_regional_evidence_from_customer_or_delivery_not_title_or_summary():
    assert is_chechnya_notice(notice("0194200000526005027",
                                    customer="Комитет правительства Чеченской Республики"))
    assert is_chechnya_notice(notice("0194200000526005028", region="г. Грозный"))
    assert not is_chechnya_notice(notice("0194200000526005029",
                                        customer="Министерство Московской области",
                                        region="Московская область",
                                        title="Доставка в Чеченскую Республику"))


def test_foreign_groznenskaya_street_is_not_chechnya_regional_proof():
    """Grozny city != a Groznenskaya street named in another region."""
    for region, customer in (
        ("Московская область, Грозненская улица", "Муниципальный заказчик МО"),
        ("Ставропольский край", "Отдел по ул. Грозненской, 5"),
        ("Москва, Грозненский проезд", "Организация Москва"),
        ("Республика Дагестан", "Грозненский участок"),
    ):
        assert not is_chechnya_notice(notice(
            "0194200000526005027", region=region, customer=customer,
        ))
    assert is_chechnya_notice(notice(
        "0194200000526005027", region="г. Грозного",
    ))
    assert is_chechnya_notice(notice(
        "0194200000526005027", region="Чеченской Республики",
    ))


def test_only_verified_region_procedures_leave_adapter(monkeypatch):
    async def synthetic_upstream(self, limit=20):
        assert self.name == SOURCE_KEY and limit == 100
        return [
            notice("0194200000526005027",
                   customer="Комитет правительства Чеченской Республики"),
            notice("0194200000526005027",
                   customer="Комитет правительства Чеченской Республики"),
            notice("0194200000526005028", region="Грозный"),
            notice("0194200000526005029", region="Москва"),
            notice("0194200000526005030", title="Объект в Чеченской Республике"),
            replace(notice("0194200000526005031", region="г. Грозный"), tender_number=None),
        ]
    monkeypatch.setattr(EisRssSource, "fetch", synthetic_upstream)
    result = asyncio.run(ChechnyaEisRssSource((URL,)).fetch(limit=5))
    assert [n.external_id for n in result] == [
        "0194200000526005027", "0194200000526005028"
    ]
    assert all(n.source == SOURCE_KEY for n in result)


def test_rejects_procedure_number_that_does_not_match_original_eis_card(monkeypatch):
    async def synthetic_upstream(self, limit=20):
        return [
            replace(notice("0194200000526005027", region="Чеченская Республика"),
                    tender_number="0194200000526005028"),
            replace(notice("0194200000526005027", region="Чеченская Республика"),
                    url="https://evil.example/epz/order/notice/ea20/view/common-info.html?regNumber=0194200000526005027"),
            notice("0194200000526005029", region="Чеченская Республика"),
        ]
    monkeypatch.setattr(EisRssSource, "fetch", synthetic_upstream)
    rows = asyncio.run(ChechnyaEisRssSource((URL,)).fetch(limit=3))
    assert [row.tender_number for row in rows] == ["0194200000526005029"]



def test_amended_rss_guids_have_one_durable_official_identity(monkeypatch):
    """Synthetic GUID rotations must not create a second original or alert."""
    from app.sources.enrichment import enrichment, validate_enrichment
    from app.sources.opportunities import validate_notice

    number = "0194200000526005027"
    base = notice(number, customer="Комитет Правительства Чеченской Республики")
    first = replace(
        base, external_id="rss-guid-version-1",
        enrichment=enrichment(SOURCE_KEY, "rss-guid-version-1"),
    )
    amendment = replace(
        base, external_id="rss-guid-version-2",
        title="Поставка продуктов питания (изменение)",
        enrichment=enrichment(SOURCE_KEY, "rss-guid-version-2"),
    )

    async def different_guids(self, limit=20):
        assert limit == 100
        return [first, amendment]

    monkeypatch.setattr(EisRssSource, "fetch", different_guids)
    accepted = asyncio.run(ChechnyaEisRssSource((URL,)).fetch(limit=5))
    assert len(accepted) == 1
    assert accepted[0].external_id == number
    assert accepted[0].tender_number == number
    assert original_notice_key(accepted[0]) == ("eis_44", number)
    assert validate_notice(accepted[0], SOURCE_KEY) is accepted[0]
    assert validate_enrichment(accepted[0].enrichment, SOURCE_KEY, number)

    async def amended_only(self, limit=20):
        return [amendment]

    monkeypatch.setattr(EisRssSource, "fetch", amended_only)
    newer = asyncio.run(ChechnyaEisRssSource((URL,)).fetch(limit=5))
    assert len(newer) == 1
    assert newer[0].identity == accepted[0].identity
    assert validate_notice(newer[0], SOURCE_KEY) is newer[0]

    # Actual disposable SQLite regression: changed upstream GUID must UPDATE
    # the original procedure, not INSERT a second opportunity.
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    from app.jobs import JobRepository
    from app.sources.opportunities import OpportunityRepository

    with tempfile.TemporaryDirectory(prefix="chechnya-guid-regression-") as tmp:
        db = Database(DatabaseSettings("", Path(tmp) / "procurements.sqlite"))
        try:
            JobRepository(db).initialize()
            repository = OpportunityRepository(db)
            repository.initialize()
            version = connector_version(SOURCE_KEY)
            assert repository.upsert(accepted[0], version)
            assert not repository.upsert(newer[0], version)
            stored = repository.read(SOURCE_KEY, limit=10)
            assert len(stored) == 1
            assert stored[0].external_id == number
            assert stored[0].title == "Поставка продуктов питания (изменение)"
            assert validate_enrichment(stored[0].enrichment, SOURCE_KEY, number)
        finally:
            db.close()



def test_eis_44_original_law_is_checked_before_regional_normalization():
    sample = (
        '<rss version="2.0"><channel><item>'
        '<title>Поставка продуктов</title>'
        '<guid>0194200000526005027</guid>'
        '<link>' + EIS_ORIGINAL.replace("&", "&amp;") + '</link>'
        '<description>Размещение выполняется по: 44-ФЗ. '
        'Регион: Чеченская Республика; '
        'Заказчик: Комитет Правительства Чеченской Республики</description>'
        '</item></channel></rss>'
    ).encode("utf-8")
    verify_eis_feed_law(sample, "44-FZ")
    items = parse_eis_feed(sample, source_name=SOURCE_KEY)
    assert len(items) == 1 and items[0].tender_number == "0194200000526005027"
    assert is_chechnya_notice(items[0])



def test_official_card_number_wins_over_unrelated_19_digit_description_id():
    """An EIS description referencing another procurement must not drop real notice."""
    other = "0373100100726000010"
    official = "0194200000526005027"
    sample = (
        '<rss version="2.0"><channel><item>'
        '<title>Сопутствующая закупка ' + other + '</title>'
        '<guid>upstream-update-guid-a</guid>'
        '<link>' + EIS_ORIGINAL + '</link>'
        '<description>Справка: ' + other + '; '
        'Размещение выполняется по: 44-ФЗ. '
        'Регион: Чеченская Республика; '
        'Заказчик: Комитет Правительства Чеченской Республики'
        '</description></item></channel></rss>'
    ).encode("utf-8")
    verify_eis_feed_law(sample, "44-FZ")
    regional = parse_eis_feed(sample, source_name=SOURCE_KEY)
    assert len(regional) == 1
    assert regional[0].tender_number == official
    assert is_chechnya_notice(regional[0])
    # Existing national adapter semantics are not silently changed here.
    national = parse_eis_feed(sample, source_name="eis")
    assert national[0].tender_number == other


def test_chechnya_parser_does_not_trust_foreign_original_links():
    """Only official EIS URLs are allowed to override text-derived IDs."""
    other = "0373100100726000010"
    sample = (
        '<rss version="2.0"><channel><item>'
        '<title>Справка ' + other + '</title>'
        '<guid>upstream-update-guid-b</guid>'
        '<link>https://evil.example/epz/order/notice/ea20/view/common-info.html'
        '?regNumber=0194200000526005027</link>'
        '<description>Регион: Чеченская Республика; '
        'Заказчик: Комитет Правительства Чеченской Республики'
        '</description></item></channel></rss>'
    ).encode("utf-8")
    regional = parse_eis_feed(sample, source_name=SOURCE_KEY)
    assert regional[0].tender_number == other


def test_enabled_without_operator_url_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("RU_CHECHNYA_EIS_ENABLED", "true")
    monkeypatch.delenv("RU_CHECHNYA_EIS_RSS_URLS", raising=False)
    with pytest.raises(MonitoringConfigurationError):
        load_monitoring_settings(tmp_path / "does-not-exist.env")


def test_disabled_configuration_does_not_auto_register(monkeypatch, tmp_path):
    monkeypatch.setenv("RU_CHECHNYA_EIS_ENABLED", "false")
    monkeypatch.setenv("RU_CHECHNYA_EIS_RSS_URLS", URL)
    cfg = load_monitoring_settings(tmp_path / "does-not-exist.env")
    assert not cfg.ru_chechnya_eis_enabled
    assert SOURCE_KEY not in build_source_catalog(cfg).enabled_keys


def test_same_eis_original_is_never_counted_twice_across_national_and_regional_feeds():
    from dataclasses import replace
    regional = notice('0194200000526005027', region='Чеченская Республика')
    national = replace(regional, source='eis')
    assert original_notice_key(regional) == original_notice_key(national)
    unique, duplicates = deduplicate([regional, national])
    assert len(unique) == 1 and unique[0].source == 'eis'
    assert len(duplicates) == 1


def test_live_local_alert_sink_returns_required_synthetic_receipt_only():
    """Offline: local capture ACK unblocks marking after successful send.

    Never treats a local-only test stub as Telegram API delivery.
    """
    from scripts.ci_ru_chechnya_eis_real_worker import LocalCaptureBot

    async def run():
        stop = asyncio.Event()
        bot = LocalCaptureBot(stop)
        text = "🆕 НОВАЯ ЗАКУПКА\\nИсточник: " + SOURCE_KEY
        receipt = await bot.send_message(
            99102, text, disable_web_page_preview=True,
        )
        # The shared monitor ACK gate lives in a separate unmerged PR;
        # this source-specific test only checks local receipt shape.
        assert type(receipt.message_id) is int and receipt.message_id > 0
        assert type(receipt.chat.id) is int and receipt.chat.id == 99102
        assert receipt.message_id == 1
        assert receipt.chat.id == 99102
        assert stop.is_set() and bot.messages == [text]
        with pytest.raises(AssertionError):
            await bot.send_message(12345, text, disable_web_page_preview=True)
        with pytest.raises(AssertionError):
            await bot.send_message(99102, "unverified source",
                                   disable_web_page_preview=True)
        assert len(bot.messages) == 1

    asyncio.run(run())


def test_user_notification_catalog_reads_real_worker_snapshot_not_second_rss(monkeypatch):
    """Offline boundary: monitoring must consume the persisted Worker identity."""
    from app.bot.monitoring import enabled_ru_catalog_keys
    from app.sources.snapshots import snapshot_catalog

    stored = notice(
        "0194200000526005027",
        customer="Комитет Правительства Чеченской Республики",
    )
    class IsolatedStore:
        def __init__(self):
            self.read_count = 0

        def read(self, source, limit, terms):
            assert source == SOURCE_KEY and limit == 5
            self.read_count += 1
            return [stored]

    async def forbidden_second_network_fetch(self, limit=20):
        raise AssertionError("No fresh EIS fetch after leased Worker persisted original")

    monkeypatch.setattr(ChechnyaEisRssSource, "fetch", forbidden_second_network_fetch)
    catalog = build_source_catalog(
        replace(settings(), ru_chechnya_eis_enabled=True,
                ru_chechnya_eis_rss_urls=(URL,))
    )
    store = IsolatedStore()
    persisted = snapshot_catalog(catalog, store)
    assert enabled_ru_catalog_keys(persisted) == (SOURCE_KEY,)
    rows = asyncio.run(persisted.registry.get(SOURCE_KEY).source.fetch(limit=5))
    assert rows == [stored] and store.read_count == 1


def test_chechnya_telegram_receipt_rejected_if_absent_or_wrong_chat():
    """Offline: transport completion without a valid Bot API receipt is not delivery."""
    from types import SimpleNamespace
    from app.bot.monitoring import _require_telegram_delivery_ack

    invalid = [
        None,
        SimpleNamespace(message_id=0, chat=SimpleNamespace(id=99102)),
        SimpleNamespace(message_id=9, chat=SimpleNamespace(id=99103)),
        SimpleNamespace(message_id=9, chat=None),
        SimpleNamespace(message_id="9", chat=SimpleNamespace(id=99102)),
    ]
    for receipt in invalid:
        with pytest.raises(ValueError, match="Telegram message acknowledgement invalid"):
            _require_telegram_delivery_ack(receipt, 99102)


def test_chechnya_background_does_not_claim_without_telegram_receipt():
    """Offline: Chechnya alert remains retryable if a stub returns no Telegram ACK."""
    from types import SimpleNamespace
    from app.bot.monitoring import monitor_loop

    async def scenario():
        stop = asyncio.Event()
        item = SimpleNamespace(
            notice=notice("0194200000526005027", region="Чеченская Республика"),
            reasons=("Поставка",),
        )

        class FakeRegistry:
            def metadata(self):
                return (SimpleNamespace(key=SOURCE_KEY, enabled=True,
                                        jurisdictions=("RU",)),)

        class FakeCatalog:
            registry = FakeRegistry()

        class FakeService:
            settings = replace(settings(), enabled=True,
                               ru_background_catalog_enabled=True,
                               max_notifications_per_cycle=1)

            async def active_subscriptions(self):
                return [SimpleNamespace(owner_user_id=99101, chat_id=99102)]

            async def fetch_matches_from_catalog(self, catalog, owner_user_id,
                                                 *, source_keys):
                assert source_keys == (SOURCE_KEY,)
                return [item], SimpleNamespace(
                    attempted_sources=(SOURCE_KEY,), total_failure=False
                )

            async def unseen_matches(self, owner_user_id, matches):
                return matches

            async def claim_new(self, owner_user_id, matches):
                raise AssertionError("Chechnya alert falsely marked delivered")

        class NoAckBot:
            async def send_message(self, chat_id, text, **kwargs):
                stop.set()
                return None

        await asyncio.wait_for(monitor_loop(NoAckBot(), FakeService(), stop,
                                            source_catalog=FakeCatalog()), timeout=5)

    asyncio.run(scenario())


def test_transport_probe_classifies_tls_and_dns_without_logging_raw_errors():
    """Offline: connector failures must be diagnosable without secrets or TLS bypass."""
    import socket
    import ssl
    import httpx
    from scripts.ru_chechnya_eis_transport_probe import transport_category

    for underlying, expected in (
        (ssl.SSLError("synthetic-cert-failure"), "TLS_CERTIFICATE_OR_HANDSHAKE"),
        (socket.gaierror("synthetic-dns-failure"), "DNS_RESOLUTION_FAILED"),
    ):
        try:
            raise httpx.ConnectError("synthetic-eis-url") from underlying
        except httpx.ConnectError as error:
            assert transport_category(error) == expected

    assert transport_category(httpx.ConnectTimeout("synthetic")) == "TIMEOUT"
    assert transport_category(httpx.ConnectError("synthetic")) == "CONNECT_FAILED_UNCLASSIFIED"

    # Production bounded transport redacts raw URL, so operators must retain
    # actionable safe categories without relying on httpx message text.
    from app.sources.http import ConnectorTransportError
    for reason, expected in (
        ("tls_certificate", "TLS_CERTIFICATE_OR_HANDSHAKE"),
        ("public_ip", "DNS_NONPUBLIC_IP_REJECTED"),
        ("network", "NETWORK_TRANSPORT_FAILED"),
        ("http_status", "HTTP_REJECTED"),
        ("http_transient", "HTTP_TRANSIENT"),
        ("response_size", "OVER_SIZE_LIMIT"),
    ):
        assert transport_category(ConnectorTransportError(reason=reason)) == expected


def test_offline_probe_only_counts_verified_official_chechnya_rss(monkeypatch):
    """MockTransport-like injection: no network, no production writes or Telegram."""
    from scripts import ru_chechnya_eis_transport_probe as probe

    sample = (
        '<rss version="2.0"><channel><item>'
        '<title>Поставка продуктов питания</title>'
        '<guid>first-rss-update-id</guid>'
        '<link>' + EIS_ORIGINAL.replace("&", "&amp;") + '</link>'
        '<description>Размещение выполняется по: 44-ФЗ. '
        'Регион: Чеченская Республика; '
        'Заказчик: Комитет Правительства Чеченской Республики</description>'
        '</item></channel></rss>'
    ).encode("utf-8")

    import httpx
    from app.sources.http import BoundedClient

    requests = []

    def official_http_response(request):
        requests.append((request.url.host, request.url.path, request.url.params.get("fz44")))
        assert request.url.host == "zakupki.gov.ru"
        return httpx.Response(
            200, content=sample, headers={"content-type": "application/rss+xml"},
        )

    def bounded_client_with_offline_transport(**kwargs):
        assert kwargs["verify"] is True
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        return BoundedClient(
            **kwargs, transport=httpx.MockTransport(official_http_response),
        )

    cfg = replace(settings(), ru_chechnya_eis_enabled=True,
                  ru_chechnya_eis_rss_urls=(URL,), eis_direct_enabled=True)
    monkeypatch.setattr(probe, "load_monitoring_settings", lambda: cfg)
    monkeypatch.setattr(probe, "source_client", bounded_client_with_offline_transport)
    result = probe.run_probe()
    assert result["state"] == "VERIFIED_FEED_WITH_ACCEPTED_ORIGINALS"
    assert result["official_item_count"] == 1
    assert result["regional_evidence_count"] == 1
    assert result["accepted_original_count"] == 1
    assert requests == [("zakupki.gov.ru", "/epz/order/extendedsearch/rss.html", "on")]
    assert not result["worker_sqlite_verified"]
    assert not result["telegram_delivery_verified"]

    # Still a valid EIS 44-FZ XML route and Chechnya customer, but the
    # original number is not a 19-digit procedure. The Worker would reject
    # it: network diagnostics MUST NOT claim ingestible verified tenders.
    sample = sample.replace(b"0194200000526005027", b"019420000052600502")
    rejected = probe.run_probe()
    assert rejected["official_item_count"] == 1
    assert rejected["regional_evidence_count"] == 1
    assert rejected["accepted_original_count"] == 0
    assert rejected["state"] == "VALID_FEED_NO_ACCEPTED_ORIGINALS"



def test_optional_authorized_telegram_api_check_never_sends_without_opt_in(monkeypatch):
    """Offline: missing test-chat credentials must not call Bot API."""
    from scripts import ci_ru_chechnya_eis_real_worker as harness
    monkeypatch.delenv("RU_CHECHNYA_E2E_TEST_BOT_TOKEN", raising=False)
    monkeypatch.delenv("RU_CHECHNYA_E2E_TEST_CHAT_ID", raising=False)

    def forbid_bot(*args, **kwargs):
        raise AssertionError("No Telegram API connection without authorized opt-in")

    monkeypatch.setattr(harness, "Bot", forbid_bot)
    result = asyncio.run(harness.optional_authorized_telegram_api_check(
        notice("0194200000526005027", region="Чеченская Республика"),
    ))
    assert result is False
    monkeypatch.setenv("RU_CHECHNYA_E2E_TEST_CHAT_ID", "-1001234567890")
    with pytest.raises(AssertionError, match="Both authorized"):
        asyncio.run(harness.optional_authorized_telegram_api_check(
            notice("0194200000526005027", region="Чеченская Республика"),
        ))


def test_optional_test_telegram_requires_matching_real_api_ack(monkeypatch):
    """Offline fake Bot transport exercises the real gated send path."""
    from types import SimpleNamespace
    from scripts import ci_ru_chechnya_eis_real_worker as harness

    monkeypatch.setenv("RU_CHECHNYA_E2E_TEST_BOT_TOKEN", "synthetic_test_only")
    monkeypatch.setenv("RU_CHECHNYA_E2E_TEST_CHAT_ID", "-1001234567890")
    recorded = []

    class FakeBot:
        def __init__(self, *, token):
            assert token == "synthetic_test_only"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def send_message(self, *, chat_id, text, disable_web_page_preview):
            assert chat_id == -1001234567890
            assert disable_web_page_preview is True
            assert "0194200000526005027" in text
            assert text.count("\n") >= 3
            assert "\\n" not in text
            assert "Источник: " + SOURCE_KEY in text
            assert "Номер: 0194200000526005027" in text
            recorded.append(text)
            return SimpleNamespace(
                message_id=44, chat=SimpleNamespace(id=chat_id),
            )

    monkeypatch.setattr(harness, "Bot", FakeBot)
    original = notice("0194200000526005027", region="Чеченская Республика")
    assert asyncio.run(harness.optional_authorized_telegram_api_check(original)) is True
    assert len(recorded) == 1

    # Even when the operator configured a test chat, never allow an unverified
    # or foreign original across the external-send boundary.
    for tampered in (
        replace(original, region="Москва"),
        replace(original, url="https://evil.example/epz/order/notice/ea20/view/common-info.html?regNumber=0194200000526005027"),
        replace(original, external_id="changing-rss-guid"),
    ):
        with pytest.raises(AssertionError, match="Only verified official regional"):
            asyncio.run(harness.optional_authorized_telegram_api_check(tampered))
    assert len(recorded) == 1

    class WrongChatBot(FakeBot):
        async def send_message(self, *, chat_id, text, disable_web_page_preview):
            return SimpleNamespace(
                message_id=45, chat=SimpleNamespace(id=999),
            )

    monkeypatch.setattr(harness, "Bot", WrongChatBot)
    with pytest.raises(ValueError, match="Telegram message acknowledgement invalid"):
        asyncio.run(harness.optional_authorized_telegram_api_check(original))


def test_strict_acceptance_full_offline_worker_sqlite_query_local_alert(monkeypatch):
    """Integration regression: real parser, law, leased Worker, SQL and local alert.

    Only HTTP response bytes are synthetic; this NEVER proves live source
    availability, external Bot API receipt or production readiness.
    """
    from scripts import ci_ru_chechnya_eis_real_worker as harness

    monkeypatch.delenv("RU_CHECHNYA_E2E_TEST_BOT_TOKEN", raising=False)
    monkeypatch.delenv("RU_CHECHNYA_E2E_TEST_CHAT_ID", raising=False)
    config = replace(
        settings(),
        enabled=True, ru_background_catalog_enabled=True,
        ru_chechnya_eis_enabled=True, ru_chechnya_eis_rss_urls=(URL,),
        eis_direct_enabled=True,
    )
    monkeypatch.setattr(harness, "isolated_settings", lambda: config)
    # Synthetic EIS HTTP response is the *only* mocked boundary. Exercise the
    # production RSS XML parser + whole-feed 44-FZ law validation, source
    # normalization, lease fencing, SQLite, user search, and local alert.
    import httpx
    from app.sources import eis_rss

    xml = (
        '<rss version="2.0"><channel><item>'
        '<title>Поставка продуктов питания</title>'
        '<guid>amended-public-eis-rss-guid</guid>'
        '<link>' + EIS_ORIGINAL.replace("&", "&amp;") + '</link>'
        '<description>'
        'Размещение выполняется по: 44-ФЗ; '
        'Регион: Чеченская Республика; '
        'Заказчик: Комитет Правительства Чеченской Республики; '
        'Номер закупки 0194200000526005027'
        '</description></item></channel></rss>'
    ).encode("utf-8")
    sent = []

    def official_fixture_only(request):
        assert request.url.host == "zakupki.gov.ru"
        assert request.url.path == "/epz/order/extendedsearch/rss.html"
        assert request.url.params.get("fz44") == "on"
        sent.append(str(request.url.path))
        return httpx.Response(
            200, content=xml, headers={"content-type": "application/rss+xml"},
        )

    def mock_public_client(**kwargs):
        # Keep the real bounded public-source client policy and strict direct
        # HTTPS behavior; exchange only the outgoing socket for MockTransport.
        from app.sources.http import BoundedClient
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        return BoundedClient(
            **kwargs, transport=httpx.MockTransport(official_fixture_only),
        )

    monkeypatch.setattr(eis_rss, "source_client", mock_public_client)
    result = harness.accept()
    assert sent == ["/epz/order/extendedsearch/rss.html"]
    assert result["official_live_eis_region_notices"] == 1
    assert result["fenced_worker_inserted"] == 1
    assert result["sqlite_original_number_query"]
    assert result["sqlite_real_title_keyword_query"]
    assert result["unmatched_keyword_returns_none"]
    assert result["local_alert_captured"] == 1
    assert result["local_alert_replay_dedup_verified"]
    assert result["real_telegram_api_delivery_verified"] is False
    assert result["production_enabled"] is False
