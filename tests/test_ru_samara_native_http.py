"""Synthetic OFFLINE protocol tests. No fabricated output is live tender evidence."""
import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import scripts.research_ru_samara_native_http as mod
from app.sources.http import _policy


TOKEN = "A" * 36
INDEX = (f'<script>const url="{mod.JSON_PATH}";</script>'
         f'<div class="grid_filter"><input name="__RequestVerificationToken" '
         f'value="{TOKEN}"></div>').encode("utf-8")


def synthetic_body(count=2):
    return json.dumps({"items": [
        {"number": f"ИМЗ-2026-{n:07d}",
         "name": "Synthetic office equipment request",
         "uchr_sname": "Synthetic Samara municipality",
         "link": f"/smallpurchases/GzwSP/{5611000+n}"}
        for n in range(count)
    ]}, ensure_ascii=False).encode()


class Reply:
    def __init__(self, body, mime):
        self.content = body
        self.headers = {"content-type": mime}

    def raise_for_status(self):
        pass


def test_exact_same_origin_anonymous_two_request_contract(monkeypatch):
    seen = []
    class Client:
        async def get(self, url, **kwargs):
            seen.append(("GET", url))
            assert url == mod.GRID
            assert kwargs["headers"]["Accept"] == "text/html"
            return Reply(INDEX, "text/html")

        async def post(self, url, **kwargs):
            seen.append(("POST", url))
            assert url == mod.URL
            assert set(kwargs) == {"json", "headers"}
            assert kwargs["json"] == {"settings": mod.public_settings()}
            assert kwargs["headers"]["RequestVerificationToken"] == TOKEN
            assert kwargs["headers"]["Referer"] == mod.GRID
            assert kwargs["headers"]["X-Requested-With"] == "XMLHttpRequest"
            return Reply(synthetic_body(), "application/json")

    @asynccontextmanager
    async def client(**kwargs):
        assert not kwargs["trust_env"] and not kwargs["follow_redirects"]
        assert _policy.get().hosts == frozenset({mod.HOST})
        assert _policy.get().max_requests == 2
        yield Client()

    monkeypatch.setattr(mod, "source_client", client)
    assert asyncio.run(mod.proof()) == {
        "rows": 2, "native_ids": 2, "same_host_detail_refs": 2}
    assert seen == [("GET", mod.GRID), ("POST", mod.URL)]


@pytest.mark.parametrize("html,json_bytes,mime", [
    (b"<html>Login</html>", synthetic_body(), "application/json"),
    (INDEX.replace(TOKEN.encode(), b""), synthetic_body(), "application/json"),
    (INDEX, synthetic_body(0), "application/json"),
    (INDEX, synthetic_body(1), "application/json"),
    (INDEX, b"<html>Login</html>", "text/html"),
    (INDEX, b"{bad json}", "application/json"),
])
def test_missing_csrf_bad_schema_and_empty_results_fail_closed(monkeypatch, html, json_bytes, mime):
    class Client:
        async def get(self, url, **kwargs):
            return Reply(html, "text/html")
        async def post(self, url, **kwargs):
            return Reply(json_bytes, mime)

    @asynccontextmanager
    async def client(**kwargs):
        yield Client()

    monkeypatch.setattr(mod, "source_client", client)
    with pytest.raises(ValueError):
        asyncio.run(mod.proof())
