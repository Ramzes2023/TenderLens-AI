import asyncio

import httpx
import pytest

from app.sources import (
    TED_SEARCH_URL,
    TedApiSource,
    parse_ted_search_response,
)
from app.sources.eis_rss import SourceError


def test_parse_ted_search_response_normalizes_notice() -> None:
    payload = {
        "notices": [
            {
                "publication-number": "123456-2026",
                "notice-title": {
                    "deu": "Deutscher Titel",
                    "eng": "Supply of laboratory equipment",
                },
                "buyer-name": ["Example Contracting Authority"],
                "publication-date": "2026-10-04",
                "deadline-receipt-tender-date-lot": [
                    "2026-11-10"
                ],
                "total-value": "1250000.50",
                "total-value-cur": "EUR",
                "place-of-performance": [
                    "DE",
                    "DE",
                    "Berlin",
                ],
                "description-proc": {
                    "eng": "Laboratory equipment procurement."
                },
            }
        ]
    }

    notices = parse_ted_search_response(payload)

    assert len(notices) == 1

    notice = notices[0]

    assert notice.source == "ted"
    assert notice.external_id == "123456-2026"
    assert notice.tender_number == "123456-2026"
    assert notice.title == "Supply of laboratory equipment"
    assert notice.customer == "Example Contracting Authority"
    assert notice.published_at == "2026-10-04"
    assert notice.deadline == "2026-11-10"
    assert notice.initial_price == 1250000.50
    assert notice.currency == "EUR"
    assert notice.region == "DE, Berlin"
    assert notice.summary == "Laboratory equipment procurement."
    assert notice.url == (
        "https://ted.europa.eu/en/notice/123456-2026/html"
    )


def test_parser_requires_publication_number() -> None:
    with pytest.raises(SourceError):
        parse_ted_search_response(
            {
                "notices": [
                    {
                        "notice-title": "Missing identifier",
                    }
                ]
            }
        )


def test_parser_rejects_invalid_envelope() -> None:
    with pytest.raises(SourceError):
        parse_ted_search_response(
            {
                "notices": "not-a-list",
            }
        )


def test_ted_source_posts_official_search_contract(
    monkeypatch,
) -> None:
    captured = {}

    class FakeResponse:
        content = b'{"notices": []}'

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"notices": []}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(
            self,
            exc_type,
            exc,
            traceback,
        ):
            return False

        async def post(self, url, *, json):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(
        "app.sources.ted_api.httpx.AsyncClient",
        FakeClient,
    )

    result = asyncio.run(
        TedApiSource().fetch(limit=25)
    )

    assert result == []
    assert captured["url"] == TED_SEARCH_URL
    assert captured["json"]["limit"] == 25
    assert captured["json"]["page"] == 1
    assert captured["json"]["scope"] == "ACTIVE"
    assert captured["json"]["paginationMode"] == "PAGE_NUMBER"
    assert captured["json"]["query"].startswith("OJ = ()")
    assert "publication-number" in captured["json"]["fields"]


def test_ted_source_clamps_limit_to_100(
    monkeypatch,
) -> None:
    captured = {}

    class FakeResponse:
        content = b'{"notices": []}'

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"notices": []}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(
            self,
            exc_type,
            exc,
            traceback,
        ):
            return False

        async def post(self, url, *, json):
            captured["limit"] = json["limit"]
            return FakeResponse()

    monkeypatch.setattr(
        "app.sources.ted_api.httpx.AsyncClient",
        FakeClient,
    )

    asyncio.run(
        TedApiSource().fetch(limit=999)
    )

    assert captured["limit"] == 100


def test_ted_source_wraps_http_failure(
    monkeypatch,
) -> None:
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(
            self,
            exc_type,
            exc,
            traceback,
        ):
            return False

        async def post(self, url, *, json):
            raise httpx.ConnectError("offline")

    monkeypatch.setattr(
        "app.sources.ted_api.httpx.AsyncClient",
        FakeClient,
    )

    with pytest.raises(
        SourceError,
        match="Unable to fetch TED notices",
    ):
        asyncio.run(
            TedApiSource().fetch()
        )
