"""First-party list-only Samara adapter hostile fixtures (not live originals)."""
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
import asyncio
import copy

import pytest
import app.sources.ru_samara_public_list as mod

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
         "uchr_sname": "Городская больница Самарской области",
         "summa": "100 000,00",
         "pub_date": "19.10.2026",
         "collecting_enddate": "22.10.2026"},
        {"link": "/smallpurchases/GzwSP/5611196",
         "number": "ИМЗ-2026-100002",
         "name": "Обслуживание компьютерной сети школы",
         "uchr_sname": "Муниципальная школа",
         "summa": "200 000,00",
         "pub_date": "19.10.2026",
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
    assert all(n.published_at == "19.10.2026" for n in items)
    assert "авторизац" in items[0].summary


@pytest.mark.parametrize("mutator", [
    lambda d: d.update(items=[]),
    lambda d: d.update(totalRows=1),
    lambda d: d.update(totalRows="21739"),
    lambda d: d["items"][0].update(link="https://evil.example/smallpurchases/GzwSP/5611345"),
    lambda d: d["items"][0].update(link="http://webtorgi.samregion.ru/smallpurchases/GzwSP/5611345"),
    lambda d: d["items"][0].update(link="/smallpurchases/GzwSP/5611345?token=x"),
    lambda d: d["items"][0].update(link="javascript:alert(1)"),
    lambda d: d["items"][0].update(link="/smallpurchases/GzwSP/5611196"),
    lambda d: d["items"][0].update(name="<script>fake tender</script>"),
    lambda d: d["items"][0].update(name=""),
    lambda d: d["items"][0].update(uchr_sname=""),
    lambda d: d["items"][0].update(number="ИМЗ-2026-100002"),
    lambda d: d["items"][0].update(number=""),
    lambda d: d["items"][0].update(number="НЕ-ИМЗ-2026-100001"),
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
    actual=asyncio.run(mod.SamaraPublicListSource().fetch(limit=2))
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
        ru_samara_public_list_enabled=True,
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


def test_verified_two_pages_return_20_distinct_native_notices_in_three_requests(monkeypatch):
    from app.sources.http import _policy

    first = original_rows()["items"][0]
    pages = []
    for idx in range(2):
        rows = []
        for j in range(10):
            record = copy.deepcopy(first)
            n = 20 * idx + j + 1
            record["link"] = f"/smallpurchases/GzwSP/{5611000+n}"
            record["number"] = f"ИМЗ-2026-{n:06d}"
            record["name"] = f"Настоящий по форме синтетический тест страницы {idx} запись {n}"
            rows.append(record)
        pages.append({"items": rows, "totalRows": 20, "page": idx})
    observed = []

    class Reply:
        headers = {"content-type": "application/json"}
        content = b'{"items":[]}'
        def __init__(self, payload):
            self.payload = payload
        def raise_for_status(self):
            pass
        def json(self):
            return self.payload

    class Client:
        async def get(self, url):
            observed.append(("GET", url))
            return SimpleNamespace(
                content=index_html(), headers={"content-type": "text/html"},
                raise_for_status=lambda: None,
            )
        async def post(self, url, **kwargs):
            idx = kwargs["json"]["settings"]["page"]
            observed.append(("POST", idx))
            assert kwargs["headers"]["RequestVerificationToken"] == TOKEN
            assert _policy.get().hosts == frozenset({mod.HOST})
            assert _policy.get().max_requests == 3
            return Reply(pages[idx])

    @asynccontextmanager
    async def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield Client()

    monkeypatch.setattr(mod, "source_client", client)
    items = asyncio.run(mod.SamaraPublicListSource().fetch(limit=20))
    assert observed == [("GET", mod.GRID), ("POST", 0), ("POST", 1)]
    assert len(items) == len({n.external_id for n in items}) == 20
    assert len({n.tender_number for n in items}) == 20
    assert all(x.url == mod.GRID for x in items)
    assert all(x.deadline == "22.10.2026" and x.initial_price == 100000.0 for x in items)


def test_repeated_original_across_pages_fails_closed(monkeypatch):
    first = original_rows()["items"][0]
    data = {"items": [copy.deepcopy(first) for _ in range(10)], "totalRows": 20}
    for i, row in enumerate(data["items"]):
        row["number"] = f"ИМЗ-2026-{i+1:06d}"
        row["link"] = f"/smallpurchases/GzwSP/{5611001+i}"
    second = copy.deepcopy(data)
    # Each page is valid alone, but the same first-party IDs across pages
    # cannot become twenty artificial unique procurement notices.
    class Reply:
        content = b"{}"
        headers = {"content-type": "application/json"}
        def __init__(self, obj):
            self.obj = obj
        def json(self):
            return self.obj
        def raise_for_status(self):
            pass

    class Client:
        async def get(self, url):
            return SimpleNamespace(
                content=index_html(), headers={"content-type":"text/html"},
                raise_for_status=lambda: None,
            )
        async def post(self, url, **kwargs):
            return Reply(data if kwargs["json"]["settings"]["page"] == 0 else second)

    @asynccontextmanager
    async def client(**kwargs):
        yield Client()
    monkeypatch.setattr(mod, "source_client", client)
    with pytest.raises(ValueError, match="across native pages"):
        asyncio.run(mod.SamaraPublicListSource().fetch(limit=20))


@pytest.mark.parametrize("raw,expected", [
    ("200 000,00", 200000.0), ("150000.75", 150000.75),
    ("150000,75", 150000.75), (25000, 25000.0),
    (0, None), (float("inf"), None), (float("nan"), None),
    pytest.param(10**10000, None, id="oversized-native-positive"),
    pytest.param(-(10**10000), None, id="oversized-native-negative"),
    (10**308, None), (1e18, 1e18), (False, None),
    ("-100", None), ("1e99", None), ("1,000.00", None),
    ("<script>1000</script>", None), (True, None),
])
def test_samara_list_amount_never_invents_values(raw, expected):
    assert mod.public_amount(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("19.10.2026", "19.10.2026"),
    ("19.10.2026 12:30", "19.10.2026 12:30"),
    ("19.10.2026 12:30:45", "2026-10-19T12:30:45"),
    ("32.10.2026", None), ("19.13.2026", None),
    ("19.10.2026 25:88", None), ("", None),
    ("<script>19.10.2026</script>", None), (False, None),
])
def test_samara_source_grid_dates_do_not_fabricate_time(raw, expected):
    assert mod.public_grid_date(raw) == expected


def test_large_native_json_price_is_optional_not_a_whole_real_page_failure():
    # A malformed optional 'summa' must not prevent valid original IDs,
    # title, buyer, deadline or later notices from reaching the Worker.
    payload = original_rows()
    payload["items"][0]["summa"] = 10**10000
    payload["items"][1]["summa"] = "200 000,00"
    received = mod.parse_public_list(payload)
    assert [notice.external_id for notice in received] == ["5611345", "5611196"]
    assert received[0].initial_price is None
    assert received[0].currency is None
    assert received[0].published_at == "19.10.2026"
    assert received[0].deadline == "22.10.2026"
    assert received[1].initial_price == 200000.0
    assert received[1].currency == "RUB"
    assert all(notice.url == mod.GRID for notice in received)


def test_native_price_boolean_and_nan_do_not_claim_ruble_value():
    for invalid in (True, False, float("nan"), float("inf"), float("-inf")):
        payload = original_rows()
        payload["items"][0]["summa"] = invalid
        notice = mod.parse_public_list(payload, limit=1)[0]
        assert notice.initial_price is None and notice.currency is None


def test_native_camelcase_deadline_from_official_sort_columns_is_preserved():
    assert mod.SORT_COLUMNS["collecting_endDate"] == "Дата окончания подачи заявок"
    original = original_rows()
    for row in original["items"]:
        row["collecting_endDate"] = row.pop("collecting_enddate")
    results = mod.parse_public_list(original)
    assert [notice.deadline for notice in results] == [
        "22.10.2026", "25.10.2026",
    ]
    assert [notice.external_id for notice in results] == ["5611345", "5611196"]
    assert all(n.url == mod.GRID for n in results)


def test_disagreeing_publisher_deadline_keys_remain_absent_not_invented():
    original = original_rows()
    original["items"][0]["collecting_endDate"] = "23.10.2026"
    notices = mod.parse_public_list(original)
    assert notices[0].deadline is None
    assert notices[1].deadline == "25.10.2026"
    assert notices[0].tender_number == "ИМЗ-2026-100001"
    assert notices[0].initial_price == 100000.0


@pytest.mark.parametrize("original", [
    {"collecting_endDate": "22.10.2026"},
    {"collecting_enddate": "22.10.2026"},
    {"collecting_endDate": "22.10.2026", "collecting_enddate": "22.10.2026"},
])
def test_native_deadline_equivalent_keys_are_accepted_without_guessing(original):
    assert mod.public_deadline(original) == "22.10.2026"


@pytest.mark.parametrize("original", [
    {"collecting_endDate": "32.10.2026"},
    {"collecting_endDate": "20.10.2026", "collecting_enddate": "21.10.2026"},
    {"collecting_endDate": False},
    {"collecting_endDate": None},
    {},
])
def test_native_deadline_invalid_or_absent_never_gets_fabricated(original):
    assert mod.public_deadline(original) is None
