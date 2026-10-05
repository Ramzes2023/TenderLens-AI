import asyncio

import httpx
import pytest

from app.sources import (
    KZ_GOSZAKUP_ANNOUNCEMENTS_URL,
    KazakhstanGoszakupApiSource,
    parse_kz_goszakup_response,
)
from app.sources.eis_rss import SourceError


def _item(
    advert_id: int,
    *,
    number: str | None = None,
) -> dict:
    return {
        "id": advert_id,
        "number_anno": number or f"{advert_id}-1",
        "name_ru": f"??????? {advert_id}",
        "name_kz": f"????? ??? {advert_id}",
        "org_bin": "050140006873",
        "publish_date": "2026-10-05 10:30:00",
        "start_date": "2026-10-05 11:00:00",
        "end_date": "2026-10-20 18:00:00",
        "total_sum": 1250000.50,
        "ref_buy_status_id": 220,
        "system_id": 3,
    }


def test_parser_normalizes_kazakhstan_announcement() -> None:
    payload = {
        "total": 1,
        "limit": 50,
        "next_page": "",
        "items": [
            _item(
                15578184,
                number="15578184-1",
            )
        ],
    }

    notices = parse_kz_goszakup_response(
        payload
    )

    assert len(notices) == 1

    notice = notices[0]

    assert notice.source == "kz_goszakup"
    assert notice.external_id == "15578184"
    assert notice.tender_number == "15578184-1"
    assert notice.title == "??????? 15578184"
    assert notice.published_at == (
        "2026-10-05T10:30:00"
    )
    assert notice.deadline == (
        "2026-10-20T18:00:00"
    )
    assert notice.initial_price == 1250000.50
    assert notice.currency == "KZT"
    assert notice.customer == (
        "Organizer BIN 050140006873"
    )
    assert notice.region is None
    assert notice.summary == "????? ??? 15578184"
    assert notice.url == (
        "https://goszakup.gov.kz/"
        "ru/announce/index/15578184"
    )


def test_parser_prefers_kazakh_title_when_ru_missing() -> None:
    payload = {
        "items": [
            {
                "id": 42,
                "number_anno": "42-1",
                "name_ru": None,
                "name_kz": "??????? ?????????",
                "total_sum": "1000000,25",
            }
        ]
    }

    notice = parse_kz_goszakup_response(
        payload
    )[0]

    assert notice.title == "??????? ?????????"
    assert notice.initial_price == 1000000.25
    assert notice.currency == "KZT"
    assert notice.summary is None


def test_parser_requires_items_list() -> None:
    with pytest.raises(
        SourceError,
        match="invalid items",
    ):
        parse_kz_goszakup_response(
            {
                "items": "not-a-list",
            }
        )


def test_parser_requires_announcement_id() -> None:
    with pytest.raises(
        SourceError,
        match="without id",
    ):
        parse_kz_goszakup_response(
            {
                "items": [
                    {
                        "number_anno": "123-1",
                        "name_ru": "Missing ID",
                    }
                ]
            }
        )


def test_source_requires_api_token() -> None:
    with pytest.raises(
        ValueError,
        match="token must not be empty",
    ):
        KazakhstanGoszakupApiSource(
            api_token="   "
        )


def test_source_validates_timeout() -> None:
    with pytest.raises(
        ValueError,
        match="timeout",
    ):
        KazakhstanGoszakupApiSource(
            api_token="secret",
            timeout=121,
        )


def test_source_follows_official_next_page(
    monkeypatch,
) -> None:
    captured_urls: list[str] = []

    payloads = [
        {
            "total": 3,
            "limit": 2,
            "next_page": (
                "/trd-buy?page=next&search_after=102"
            ),
            "items": [
                _item(103),
                _item(102),
            ],
        },
        {
            "total": 3,
            "limit": 2,
            "next_page": "",
            "items": [
                _item(101),
            ],
        },
    ]

    class FakeResponse:
        def __init__(
            self,
            payload,
        ):
            self._payload = payload
            self.content = b"{}"

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, **kwargs):
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(
            self,
            exc_type,
            exc,
            traceback,
        ):
            return False

        async def get(self, url):
            captured_urls.append(url)
            payload = payloads[
                len(captured_urls) - 1
            ]
            return FakeResponse(payload)

    monkeypatch.setattr(
        "app.sources.kz_goszakup.httpx.AsyncClient",
        FakeClient,
    )

    result = asyncio.run(
        KazakhstanGoszakupApiSource(
            api_token="test-token",
        ).fetch(limit=3)
    )

    assert [
        notice.external_id
        for notice in result
    ] == [
        "103",
        "102",
        "101",
    ]

    assert captured_urls == [
        KZ_GOSZAKUP_ANNOUNCEMENTS_URL,
        (
            "https://ows.goszakup.gov.kz/"
            "trd-buy?page=next&search_after=102"
        ),
    ]


def test_source_clamps_limit_to_100(
    monkeypatch,
) -> None:
    first_page = {
        "total": 150,
        "limit": 50,
        "next_page": (
            "/trd-buy?page=next&search_after=101"
        ),
        "items": [
            _item(value)
            for value in range(
                150,
                100,
                -1,
            )
        ],
    }

    second_page = {
        "total": 150,
        "limit": 50,
        "next_page": (
            "/trd-buy?page=next&search_after=51"
        ),
        "items": [
            _item(value)
            for value in range(
                100,
                50,
                -1,
            )
        ],
    }

    payloads = [
        first_page,
        second_page,
    ]

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.content = b"{}"

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, **kwargs):
            self.index = 0

        async def __aenter__(self):
            return self

        async def __aexit__(
            self,
            exc_type,
            exc,
            traceback,
        ):
            return False

        async def get(self, url):
            payload = payloads[self.index]
            self.index += 1
            return FakeResponse(payload)

    monkeypatch.setattr(
        "app.sources.kz_goszakup.httpx.AsyncClient",
        FakeClient,
    )

    result = asyncio.run(
        KazakhstanGoszakupApiSource(
            api_token="test-token",
        ).fetch(limit=999)
    )

    assert len(result) == 100
    assert result[0].external_id == "150"
    assert result[-1].external_id == "51"


def test_source_rejects_external_next_page(
    monkeypatch,
) -> None:
    class FakeResponse:
        content = b"{}"

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "items": [
                    _item(100),
                ],
                "next_page": (
                    "https://evil.example/trd-buy"
                ),
            }

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

        async def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(
        "app.sources.kz_goszakup.httpx.AsyncClient",
        FakeClient,
    )

    with pytest.raises(
        SourceError,
        match="unsafe next_page",
    ):
        asyncio.run(
            KazakhstanGoszakupApiSource(
                api_token="test-token",
            ).fetch(limit=2)
        )


def test_source_rejects_conflicting_duplicate_ids(
    monkeypatch,
) -> None:
    first = _item(100)
    second = _item(100)
    second["name_ru"] = "?????? ????????"

    payloads = [
        {
            "items": [first],
            "next_page": (
                "/trd-buy?page=next&search_after=100"
            ),
        },
        {
            "items": [second],
            "next_page": "",
        },
    ]

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.content = b"{}"

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, **kwargs):
            self.index = 0

        async def __aenter__(self):
            return self

        async def __aexit__(
            self,
            exc_type,
            exc,
            traceback,
        ):
            return False

        async def get(self, url):
            payload = payloads[self.index]
            self.index += 1
            return FakeResponse(payload)

    monkeypatch.setattr(
        "app.sources.kz_goszakup.httpx.AsyncClient",
        FakeClient,
    )

    with pytest.raises(
        SourceError,
        match="conflicting duplicate",
    ):
        asyncio.run(
            KazakhstanGoszakupApiSource(
                api_token="test-token",
            ).fetch(limit=2)
        )


def test_source_wraps_http_failure_without_token(
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

        async def get(self, url):
            raise httpx.ConnectError(
                "offline"
            )

    monkeypatch.setattr(
        "app.sources.kz_goszakup.httpx.AsyncClient",
        FakeClient,
    )

    with pytest.raises(
        SourceError,
        match=(
            "Unable to fetch Kazakhstan "
            "procurement announcements"
        ),
    ) as error:
        asyncio.run(
            KazakhstanGoszakupApiSource(
                api_token="SUPER-SECRET-TOKEN",
            ).fetch()
        )

    assert (
        "SUPER-SECRET-TOKEN"
        not in str(error.value)
    )



def test_source_sends_bearer_token_only_in_headers(
    monkeypatch,
) -> None:
    captured = {}

    class FakeResponse:
        content = b'{"items": []}'

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "items": [],
                "next_page": "",
            }

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

        async def get(self, url):
            captured["url"] = url
            return FakeResponse()

    monkeypatch.setattr(
        "app.sources.kz_goszakup.httpx.AsyncClient",
        FakeClient,
    )

    result = asyncio.run(
        KazakhstanGoszakupApiSource(
            api_token="TOP-SECRET-TOKEN",
        ).fetch(limit=1)
    )

    assert result == []

    headers = captured[
        "client_kwargs"
    ]["headers"]

    assert headers["Authorization"] == (
        "Bearer TOP-SECRET-TOKEN"
    )

    assert headers["Content-Type"] == (
        "application/json"
    )

    assert (
        "TOP-SECRET-TOKEN"
        not in captured["url"]
    )


def test_source_rejects_trd_buy_prefix_escape(
    monkeypatch,
) -> None:
    class FakeResponse:
        content = b"{}"

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "items": [
                    _item(100),
                ],
                "next_page": (
                    "/trd-buy-evil?"
                    "page=next&search_after=100"
                ),
            }

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

        async def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(
        "app.sources.kz_goszakup.httpx.AsyncClient",
        FakeClient,
    )

    with pytest.raises(
        SourceError,
        match="unsafe next_page",
    ):
        asyncio.run(
            KazakhstanGoszakupApiSource(
                api_token="test-token",
            ).fetch(limit=2)
        )


def test_source_rejects_repeated_next_page(
    monkeypatch,
) -> None:
    page_url = (
        "/trd-buy?"
        "page=next&search_after=100"
    )

    payloads = [
        {
            "items": [
                _item(100),
            ],
            "next_page": page_url,
        },
        {
            "items": [
                _item(99),
            ],
            "next_page": page_url,
        },
    ]

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.content = b"{}"

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, **kwargs):
            self.index = 0

        async def __aenter__(self):
            return self

        async def __aexit__(
            self,
            exc_type,
            exc,
            traceback,
        ):
            return False

        async def get(self, url):
            payload = payloads[self.index]
            self.index += 1
            return FakeResponse(payload)

    monkeypatch.setattr(
        "app.sources.kz_goszakup.httpx.AsyncClient",
        FakeClient,
    )

    with pytest.raises(
        SourceError,
        match="repeated next_page",
    ):
        asyncio.run(
            KazakhstanGoszakupApiSource(
                api_token="test-token",
            ).fetch(limit=3)
        )
