"""Original first-party Samara page 2 is live-verified; enforce 30-row runtime contract."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import app.sources.ru_samara_public_list as mod
from app.sources.http import _policy


TOKEN = "OFFICIAL_PUBLIC_ANONYMOUS_TOKEN_FOR_MOCK_TEST"


def grid():
    return (f'<script>const url="{mod.PATH}";</script>'
            f'<div class="grid_filter"><input name="__RequestVerificationToken" '
            f'value="{TOKEN}"></div>').encode()


def pages():
    result = []
    for page in range(3):
        items = []
        for offset in range(10):
            n = page * 10 + offset + 1
            items.append({
                "link": f"/smallpurchases/GzwSP/{5610000 + n}",
                "number": f"ИМЗ-2026-0-223-{n:06d}",
                "name": f"Поставка оборудования и расходных материалов для школы {n}",
                "uchr_sname": "Муниципальное учреждение Самарской области",
            })
        result.append({"items": items, "totalRows": 30})
    return result


def install_mock(monkeypatch, payloads, observed):
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
            assert url == mod.GRID
            observed.append(("GET", url))
            return SimpleNamespace(
                content=grid(), headers={"content-type": "text/html"},
                raise_for_status=lambda: None,
            )

        async def post(self, url, **kwargs):
            assert url == mod.JSON_URL
            page = kwargs["json"]["settings"]["page"]
            assert _policy.get().hosts == frozenset({mod.HOST})
            observed.append(("POST", page, _policy.get().max_requests))
            return Reply(payloads[page])

    @asynccontextmanager
    async def client(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        yield Client()

    monkeypatch.setattr(mod, "source_client", client)


def test_three_pages_are_bounded_and_independently_searchable(monkeypatch):
    seen = []
    install_mock(monkeypatch, pages(), seen)
    result = asyncio.run(mod.SamaraPublicListSource().fetch(limit=30))
    assert seen == [("GET", mod.GRID), ("POST", 0, 4),
                    ("POST", 1, 4), ("POST", 2, 4)]
    assert len(result) == 30
    assert len({x.external_id for x in result}) == 30
    assert len({x.tender_number for x in result}) == 30
    assert all(x.url == mod.GRID for x in result)
    assert all(x.deadline is None and x.initial_price is None for x in result)


def test_twenty_record_operator_cap_cannot_fetch_unneeded_page_two(monkeypatch):
    seen = []
    install_mock(monkeypatch, pages(), seen)
    result = asyncio.run(mod.SamaraPublicListSource().fetch(limit=20))
    assert len(result) == 20
    assert seen == [("GET", mod.GRID), ("POST", 0, 3), ("POST", 1, 3)]


def test_third_page_duplicate_cross_page_identity_rejected(monkeypatch):
    responses = pages()
    responses[2]["items"][0]["link"] = responses[0]["items"][0]["link"]
    seen = []
    install_mock(monkeypatch, responses, seen)
    with pytest.raises(ValueError, match="across native pages"):
        asyncio.run(mod.SamaraPublicListSource().fetch(limit=30))
    assert seen[-1][:2] == ("POST", 2)


def test_source_always_caps_request_at_three_independently_verified_pages(monkeypatch):
    seen = []
    install_mock(monkeypatch, pages(), seen)
    rows = asyncio.run(mod.SamaraPublicListSource().fetch(limit=100))
    assert len(rows) == 30 and len(seen) == 4
