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
    assert all(n.initial_price is None and n.deadline is None for n in items)
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
    actual=asyncio.run(mod.DagestanPublicListResearchSource().fetch(limit=2))
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
