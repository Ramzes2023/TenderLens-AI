"""Offline contract fixtures; a passing test never proves real notices."""
import pytest
from scripts.research_ru_dagestan_anonymous_post import PATH
from scripts.research_ru_dagestan_public_csrf_post import public_grid_token

GOOD_TOKEN = "A" * 36
ROUTE = f'<script>var url="{PATH}";</script>'


def public_html(inner):
    return (ROUTE + '<div class="grid_filter"><form>' + inner +
            '</form></div>').encode("utf-8")


def test_only_public_grid_filter_token_is_used_not_login_token():
    login = '<div class="login"><form><input type="hidden" name="__RequestVerificationToken" value="NOT_AUTH"></form></div>'
    grid = ('<input type="hidden" name="__RequestVerificationToken" value="' +
            GOOD_TOKEN + '"><input type="text" name="query">')
    token, names = public_grid_token((login.encode() + public_html(grid)))
    assert token == GOOD_TOKEN
    assert names == ["__RequestVerificationToken", "query"]


def test_nested_grid_filter_form_remains_within_scope():
    html = public_html('<div class="inner"><input type="hidden" '
                       f'name="__RequestVerificationToken" value="{GOOD_TOKEN}"></div>')
    assert public_grid_token(html)[0] == GOOD_TOKEN


@pytest.mark.parametrize("body", [
    b"<html>No official published JSON path</html>",
    public_html("<input name='not_a_token' value='abc'>"),
    public_html('<input name="__RequestVerificationToken" value="">'),
    public_html('<input name="__RequestVerificationToken" value="a">'),
    public_html('<input name="__RequestVerificationToken" value="bad value">'),
    public_html('<input name="__RequestVerificationToken" value="../evil">'),
    public_html(
        '<input name="__RequestVerificationToken" value="' + GOOD_TOKEN + '">'
        '<input name="__RequestVerificationToken" value="' + ("B" * 36) + '">'
    ),
    (ROUTE + '<input name="__RequestVerificationToken" value="' +
     GOOD_TOKEN + '">').encode("utf-8"),
])
def test_missing_duplicate_unsafe_or_login_only_token_is_rejected(body):
    with pytest.raises(ValueError):
        public_grid_token(body)


def test_repeated_same_public_grid_token_is_unambiguous():
    grid = (
        f'<input name="__RequestVerificationToken" value="{GOOD_TOKEN}">'
        f'<input name="__RequestVerificationToken" value="{GOOD_TOKEN}">'
    )
    token, names = public_grid_token(public_html(grid))
    assert token == GOOD_TOKEN
    assert names == ["__RequestVerificationToken"]


def test_public_csrf_request_uses_main_native_settings_and_same_origin_header(monkeypatch):
    """Offline protocol fixture only; live source evidence is separately required."""
    import asyncio
    import json
    from contextlib import asynccontextmanager
    from datetime import date
    from types import SimpleNamespace

    import scripts.research_ru_dagestan_public_csrf_post as research
    from app.sources.ru_dagestan_public_list import public_settings

    expected_settings = public_settings(date(2026, 10, 19))
    monkeypatch.setattr(research, "public_settings", lambda: expected_settings)
    calls = []
    payload = {
        "items": [{"number": "SYNTHETIC-TEST-1"}, {"number": "SYNTHETIC-TEST-2"}],
        "page": 0,
        "totalRows": 2,
        "totalAmount": 2,
    }

    class Client:
        async def get(self, url, *, headers):
            calls.append(("GET", url))
            assert url == research.INDEX
            assert headers == {"Accept": "text/html"}
            return SimpleNamespace(content=public_html(
                '<input name="__RequestVerificationToken" value="' + GOOD_TOKEN + '">'
            ), headers={"content-type": "text/html"})

        async def post(self, url, **kwargs):
            calls.append(("POST", url))
            assert url == research.URL
            assert kwargs["json"] == {"settings": expected_settings}
            assert "data" not in kwargs and "content" not in kwargs
            assert kwargs["headers"]["RequestVerificationToken"] == GOOD_TOKEN
            assert kwargs["headers"]["Referer"] == research.INDEX
            assert kwargs["headers"]["X-Requested-With"] == "XMLHttpRequest"
            raw = json.dumps(payload).encode("utf-8")
            return SimpleNamespace(
                content=raw, headers={"content-type": "application/json"},
                json=lambda: payload,
            )

    @asynccontextmanager
    async def fake_source_client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield Client()

    monkeypatch.setattr(research, "source_client", fake_source_client)
    assert asyncio.run(research.probe()) == 0
    assert calls == [("GET", research.INDEX), ("POST", research.URL)]
