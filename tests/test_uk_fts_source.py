import asyncio

import httpx
import pytest

from app.sources import (
    UK_FTS_SEARCH_URL,
    UkFindTenderApiSource,
    parse_uk_fts_response,
)
from app.sources.eis_rss import SourceError


def test_parse_uk_fts_normalizes_realistic_release() -> None:
    payload = {
        "releases": [
            {
                "id": "093514-2026",
                "ocid": "ocds-h6vhtk-078017",
                "date": "2026-10-02T16:18:43+01:00",
                "tag": ["tender"],
                "description": (
                    "Additional notice information.<br/>"
                    "Supplier instructions."
                ),
                "buyer": {
                    "id": "GB-FTS-53800",
                    "name": (
                        "Hull University Teaching "
                        "Hospitals NHS Trust"
                    ),
                },
                "tender": {
                    "id": "C460160",
                    "title": (
                        "Insourced Breast USC "
                        "One-Stop Triple Assessment"
                    ),
                    "status": "active",
                    "description": (
                        "Clinical assessment<br/><br/>"
                        "Medical imaging &amp; biopsy."
                    ),
                    "value": {
                        "amount": 765000.0,
                        "currency": "GBP",
                    },
                    "tenderPeriod": {
                        "endDate": (
                            "2026-10-21T12:00:00+01:00"
                        ),
                    },
                    "items": [
                        {
                            "id": "1",
                            "deliveryAddresses": [
                                {"region": "UKE1"},
                                {"region": "UKE1"},
                            ],
                        }
                    ],
                },
            }
        ]
    }

    notices = parse_uk_fts_response(payload)

    assert len(notices) == 1

    notice = notices[0]

    assert notice.source == "uk_fts"
    assert notice.external_id == "093514-2026"
    assert notice.tender_number == "C460160"
    assert notice.title == (
        "Insourced Breast USC One-Stop Triple Assessment"
    )
    assert notice.customer == (
        "Hull University Teaching Hospitals NHS Trust"
    )
    assert notice.published_at == (
        "2026-10-02T16:18:43+01:00"
    )
    assert notice.initial_price == 765000.0
    assert notice.currency == "GBP"
    assert notice.deadline == (
        "2026-10-21T12:00:00+01:00"
    )
    assert notice.region == "UKE1"
    assert notice.summary == (
        "Clinical assessment Medical imaging & biopsy."
    )
    assert notice.url == (
        "https://www.find-tender.service.gov.uk/"
        "procurement/ocds-h6vhtk-078017"
    )


def test_parser_falls_back_to_release_description() -> None:
    payload = {
        "releases": [
            {
                "id": "000001-2026",
                "ocid": "ocds-h6vhtk-000001",
                "description": "Release description",
                "tender": {
                    "id": "T-1",
                    "title": "Example procurement",
                },
            }
        ]
    }

    notice = parse_uk_fts_response(payload)[0]

    assert notice.summary == "Release description"


def test_parser_requires_release_id() -> None:
    with pytest.raises(SourceError):
        parse_uk_fts_response(
            {
                "releases": [
                    {
                        "ocid": "ocds-h6vhtk-000001",
                        "tender": {},
                    }
                ]
            }
        )


def test_parser_requires_ocid() -> None:
    with pytest.raises(SourceError):
        parse_uk_fts_response(
            {
                "releases": [
                    {
                        "id": "000001-2026",
                        "tender": {},
                    }
                ]
            }
        )


def test_parser_rejects_invalid_envelope() -> None:
    with pytest.raises(SourceError):
        parse_uk_fts_response(
            {
                "releases": "not-a-list",
            }
        )


def test_source_validates_timeout() -> None:
    with pytest.raises(
        ValueError,
        match="timeout",
    ):
        UkFindTenderApiSource(timeout=0)


def test_source_uses_official_api_contract(
    monkeypatch,
) -> None:
    captured = {}

    class FakeResponse:
        content = b'{"releases": []}'

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"releases": []}

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

        async def get(self, url, *, params):
            captured["url"] = url
            captured["params"] = params
            return FakeResponse()

    monkeypatch.setattr(
        "app.sources.uk_fts_api.httpx.AsyncClient",
        FakeClient,
    )

    result = asyncio.run(
        UkFindTenderApiSource().fetch(limit=25)
    )

    assert result == []
    assert captured["url"] == UK_FTS_SEARCH_URL
    assert captured["params"] == {
        "stages": "tender",
        "limit": "25",
    }


def test_source_clamps_limit_to_100(
    monkeypatch,
) -> None:
    captured = {}

    class FakeResponse:
        content = b'{"releases": []}'

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"releases": []}

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

        async def get(self, url, *, params):
            captured["limit"] = params["limit"]
            return FakeResponse()

    monkeypatch.setattr(
        "app.sources.uk_fts_api.httpx.AsyncClient",
        FakeClient,
    )

    asyncio.run(
        UkFindTenderApiSource().fetch(limit=999)
    )

    assert captured["limit"] == "100"


def test_source_wraps_http_failure(
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

        async def get(self, url, *, params):
            raise httpx.ConnectError("offline")

    monkeypatch.setattr(
        "app.sources.uk_fts_api.httpx.AsyncClient",
        FakeClient,
    )

    with pytest.raises(
        SourceError,
        match=(
            "Unable to fetch UK Find a Tender notices"
        ),
    ):
        asyncio.run(
            UkFindTenderApiSource().fetch()
        )
