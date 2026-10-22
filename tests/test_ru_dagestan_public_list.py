"""First-party list-only Dagestan adapter hostile fixtures (not live originals)."""
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
import asyncio
import copy

import pytest
import app.sources.ru_dagestan_public_list as mod

TOKEN = "PUBLIC_ANONYMOUS_GRID_TOKEN_EXAMPLE_TEST_ONLY"


def index_html():
    return (f'<script>var url="{mod.PATH}";</script>'
            '<div class="grid_filter"><input name="__RequestVerificationToken" '
            f'value="{TOKEN}"></div>').encode()


def original_rows():
    return {"items": [
        {"link": "/smallpurchases/GzwSP/5611345",
         "number": "ИМЗ-2026-100001",
         "name": "Поставка мебели для городской больницы",
         "uchr_sname": "Городская больница Дагестана",
         "summa": "100 000,00",
         "pub_date": "19.10.2026",
         "collecting_enddate": "22.10.2026"},
        {"link": "/smallpurchases/GzwSP/5611196",
         "number": "ИМЗ-2026-100002",
         "name": "Обслуживание компьютерной сети школы",
         "uchr_sname": "Муниципальная школа",
         "summa": "200 000,00",
         "collecting_enddate": "25.10.2026"},
    ], "totalRows": 21739, "page": 0, "totalAmount": None}


def test_authentic_public_settings_have_fixed_safe_keys():
    x = mod.public_settings(date(2026, 10, 18))
    assert x["page"] == 0 and x["rp"] == 10
    assert x["filter"]["dtDatePubBegin"] == {
        "PName": "dtDatePubBegin", "PType": "Date", "PValue": "18.09.2026"}
    assert mod.previous_month(date(2024, 3, 31)) == "29.02.2024"


def test_original_public_rows_are_searchable_not_fake_deep_links():
    items = mod.parse_public_list(original_rows())
    assert len(items) == 2
    assert items[0].external_id == "5611345"
    assert items[1].external_id == "5611196"
    assert items[0].tender_number == "ИМЗ-2026-100001"
    assert all(n.url == mod.GRID for n in items)
    assert [n.initial_price for n in items] == [100000.0, 200000.0]
    assert [n.currency for n in items] == ["RUB", "RUB"]
    assert [n.deadline for n in items] == ["22.10.2026", "25.10.2026"]
    assert items[0].published_at == "19.10.2026"
    assert items[1].published_at is None
    assert "авторизац" in items[0].summary


@pytest.mark.parametrize("mutator", [
    lambda d: d.update(items=[]),
    lambda d: d.update(totalRows=1),
    lambda d: d.update(totalRows="21739"),
    lambda d: d["items"][0].update(link="https://evil.example/smallpurchases/GzwSP/5611345"),
    lambda d: d["items"][0].update(link="http://goszakaz.e-dag.ru/smallpurchases/GzwSP/5611345"),
    lambda d: d["items"][0].update(link="/smallpurchases/GzwSP/5611345?token=x"),
    lambda d: d["items"][0].update(link="javascript:alert(1)"),
    lambda d: d["items"][0].update(link="/smallpurchases/GzwSP/5611196"),
    lambda d: d["items"][0].update(name="<script>fake tender</script>"),
    lambda d: d["items"][0].update(name=""),
    lambda d: d["items"][0].update(uchr_sname=""),
    lambda d: d["items"][0].update(number="ИМЗ-2026-100002"),
    lambda d: d["items"][0].update(number=""),
])
def test_malicious_forged_duplicates_bad_provenance_rejected(mutator):
    data = copy.deepcopy(original_rows())
    mutator(data)
    with pytest.raises(ValueError):
        mod.parse_public_list(data)


def test_anti_csrf_token_must_come_from_original_public_grid():
    assert mod.public_token(index_html()) == TOKEN
    with pytest.raises(ValueError):
        mod.public_token(b"<html>login</html>")
    with pytest.raises(ValueError):
        mod.public_token(index_html().replace(TOKEN.encode(), b""))
    with pytest.raises(ValueError):
        mod.public_token(index_html() + index_html().replace(
            TOKEN.encode(), b"DIFFERENT_PUBLIC_GRID_TOKEN").replace(b"</div>", b"</div>"))


def test_adapter_uses_anonymous_firstparty_get_post_without_leaks(monkeypatch):
    seen = []
    class MockReply:
        def __init__(self, *, body, mime, payload=None):
            self.content, self.headers = body, {"content-type": mime}
            self.payload = payload
        def raise_for_status(self):
            pass
        def json(self):
            return self.payload

    class Client:
        async def get(self, url):
            seen.append(("GET",url))
            return MockReply(body=index_html(), mime="text/html")
        async def post(self,url,**kwargs):
            seen.append(("POST",url,kwargs))
            return MockReply(body=b'{"items":[{},{}]}',
                             mime="application/json",payload=original_rows())

    @asynccontextmanager
    async def client(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        yield Client()

    monkeypatch.setattr(mod,"source_client",client)
    actual=asyncio.run(mod.DagestanPublicListSource().fetch(limit=2))
    assert len(actual)==2
    assert [x[0] for x in seen]==["GET","POST"]
    assert seen[1][1]==mod.JSON_URL
    assert seen[1][2]["headers"]["RequestVerificationToken"]==TOKEN
    assert seen[1][2]["json"]["settings"]["page"]==0


def test_unsupported_source_never_appears_in_default_production_catalog():
    from app.sources.catalog import build_source_catalog
    from app.monitoring.config import MonitoringSettings
    settings=MonitoringSettings(
        enabled=False,interval_seconds=600,max_items=3,max_notifications_per_cycle=5,
        request_timeout=20,eis_rss_urls=(),ca_bundle_file=None,profile_feeds_enabled=False,
    )
    catalog=build_source_catalog(settings)
    assert mod.SOURCE_ID not in catalog.enabled_keys


def test_explicit_optin_uses_real_dagestan_adapter_without_detail_capability():
    from app.sources.catalog import build_source_catalog
    from app.monitoring.config import MonitoringSettings
    catalog = build_source_catalog(MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=3,
        max_notifications_per_cycle=5, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        ru_dagestan_public_list_enabled=True,
    ))
    assert mod.SOURCE_ID in catalog.enabled_keys
    item = catalog.registry.get(mod.SOURCE_ID)
    assert item.source.name == mod.SOURCE_ID
    assert item.official
    assert item.homepage_url == mod.GRID
    assert item.capabilities.documents is False
    assert item.capabilities.keyword_search is False


def test_runtime_accepts_single_notice_and_honest_empty_page():
    data = original_rows()
    assert len(mod.parse_public_list(data, limit=1)) == 1
    data['items'] = data['items'][:1]
    data['totalRows'] = 1
    assert len(mod.parse_public_list(data)) == 1
    assert mod.parse_public_list({'items': [], 'totalRows': 0}) == []
    for total in (-1, True, '0', 2):
        with pytest.raises(ValueError):
            mod.parse_public_list({'items': [], 'totalRows': total})


@pytest.mark.parametrize("raw,expected", [
    ("100 000,00", 100000.0), ("1\u00a0200,45", 1200.45),
    ("1200,50", 1200.50), (25000, 25000.0),
    (0, None), (True, None), (-1, None),
    ("1e15", None), ("<script>1</script>", None),
    ("1,200.00", None), (float("nan"), None), (float("inf"), None),
])
def test_grid_amount_never_guesses_invalid_price(raw, expected):
    assert mod.public_amount(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("22.10.2026", "22.10.2026"),
    ("22.10.2026 17:30", "22.10.2026 17:30"),
    ("22.10.2026 17:30:50", "22.10.2026 17:30:50"),
    ("32.10.2026", None), ("22.13.2026", None),
    ("22.10.2026 25:88", None), ("", None),
    (False, None), ("<script>22.10.2026</script>", None),
])
def test_grid_dates_do_not_invent_time_or_accept_hostile_values(raw, expected):
    assert mod.public_date(raw) == expected


def test_native_deadline_case_spelling_and_conflict_fail_closed():
    row = original_rows()["items"][0]
    assert mod.public_deadline(row) == "22.10.2026"
    assert mod.public_deadline({"collecting_endDate": "23.10.2026"}) == "23.10.2026"
    assert mod.public_deadline({
        "collecting_enddate": "22.10.2026", "collecting_endDate": "23.10.2026",
    }) is None


def test_invalid_optional_grid_metadata_is_omitted_without_losing_genuine_rows():
    row = original_rows()
    row["items"][0].update(
        summa="<script>5000</script>",
        pub_date="2026-99-99",
        collecting_enddate="99.10.2026",
    )
    notices = mod.parse_public_list(row)
    assert len(notices) == 2
    assert notices[0].initial_price is None
    assert notices[0].currency is None
    assert notices[0].published_at is None
    assert notices[0].deadline is None
    assert notices[0].url == mod.GRID
    assert notices[1].initial_price == 200000.0
