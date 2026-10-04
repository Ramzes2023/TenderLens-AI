import asyncio
from datetime import date

import httpx
import pytest

from app.sources import (
    SAM_GOV_SEARCH_URL,
    SamGovApiSource,
    parse_sam_gov_response,
)
from app.sources.eis_rss import SourceError


def test_parse_sam_gov_response_normalizes_opportunity() -> None:
    payload = {
        "totalRecords": 1,
        "limit": 1,
        "offset": 0,
        "opportunitiesData": [
            {
                "noticeId": "abc123def456",
                "title": "Medical equipment procurement",
                "solicitationNumber": "W81XWH-26-R-1001",
                "fullParentPathName": (
                    "DEPT OF DEFENSE."
                    "DEPT OF THE ARMY."
                    "MEDICAL COMMAND"
                ),
                "postedDate": "2026-10-01",
                "responseDeadLine": "2026-11-15T17:00:00-05:00",
                "placeOfPerformance": {
                    "city": {
                        "code": "50000",
                        "name": "Washington",
                    },
                    "state": {
                        "code": "DC",
                        "name": "District of Columbia",
                    },
                    "zip": "20001",
                    "country": {
                        "code": "USA",
                        "name": "United States",
                    },
                },
            }
        ],
    }

    notices = parse_sam_gov_response(payload)

    assert len(notices) == 1

    notice = notices[0]

    assert notice.source == "sam_gov"
    assert notice.external_id == "abc123def456"
    assert notice.title == "Medical equipment procurement"
    assert notice.tender_number == "W81XWH-26-R-1001"
    assert notice.published_at == "2026-10-01"
    assert (
        notice.customer
        == "DEPT OF DEFENSE.DEPT OF THE ARMY.MEDICAL COMMAND"
    )
    assert notice.deadline == "2026-11-15T17:00:00-05:00"
    assert notice.region == (
        "Washington, District of Columbia, DC, "
        "United States, USA, 20001"
    )
    assert notice.initial_price is None
    assert notice.currency is None
    assert notice.summary is None
    assert notice.url == (
        "https://sam.gov/opp/abc123def456/view"
    )


def test_parser_supports_documented_deadline_typo() -> None:
    payload = {
        "opportunitiesData": [
            {
                "noticeId": "notice-2",
                "title": "Example",
                "reponseDeadLine": "2026-12-01",
            }
        ]
    }

    notice = parse_sam_gov_response(payload)[0]

    assert notice.deadline == "2026-12-01"


def test_parser_uses_legacy_org_fallback() -> None:
    payload = {
        "opportunitiesData": [
            {
                "noticeId": "notice-3",
                "title": "Example",
                "department": "DEPT A",
                "subTier": "AGENCY B",
                "office": "OFFICE C",
            }
        ]
    }

    notice = parse_sam_gov_response(payload)[0]

    assert notice.customer == (
        "DEPT A / AGENCY B / OFFICE C"
    )


def test_parser_requires_notice_id() -> None:
    with pytest.raises(SourceError):
        parse_sam_gov_response(
            {
                "opportunitiesData": [
                    {
                        "title": "Missing identifier",
                    }
                ]
            }
        )


def test_parser_rejects_invalid_envelope() -> None:
    with pytest.raises(SourceError):
        parse_sam_gov_response(
            {
                "opportunitiesData": "not-a-list",
            }
        )


def test_source_requires_api_key() -> None:
    with pytest.raises(
        ValueError,
        match="API key must not be empty",
    ):
        SamGovApiSource(api_key="   ")


def test_source_validates_lookback_days() -> None:
    with pytest.raises(
        ValueError,
        match="lookback_days",
    ):
        SamGovApiSource(
            api_key="secret",
            lookback_days=366,
        )


def test_date_range_uses_required_sam_format() -> None:
    source = SamGovApiSource(
        api_key="secret",
        lookback_days=7,
    )

    posted_from, posted_to = source._date_range(
        today=date(2026, 10, 4),
    )

    assert posted_from == "09/27/2026"
    assert posted_to == "10/04/2026"


def test_sam_source_posts_official_search_contract(
    monkeypatch,
) -> None:
    captured = {}

    class FakeResponse:
        content = b'{"opportunitiesData": []}'

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"opportunitiesData": []}

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
        "app.sources.sam_gov_api.httpx.AsyncClient",
        FakeClient,
    )

    result = asyncio.run(
        SamGovApiSource(
            api_key="test-key",
            lookback_days=7,
        ).fetch(limit=25)
    )

    assert result == []
    assert captured["url"] == SAM_GOV_SEARCH_URL
    assert captured["params"]["api_key"] == "test-key"
    assert captured["params"]["limit"] == "25"
    assert captured["params"]["offset"] == "0"

    posted_from = captured["params"]["postedFrom"]
    posted_to = captured["params"]["postedTo"]

    assert len(posted_from) == 10
    assert len(posted_to) == 10
    assert posted_from[2] == "/"
    assert posted_from[5] == "/"
    assert posted_to[2] == "/"
    assert posted_to[5] == "/"


def test_sam_source_clamps_limit_to_100(
    monkeypatch,
) -> None:
    captured = {}

    class FakeResponse:
        content = b'{"opportunitiesData": []}'

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"opportunitiesData": []}

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
        "app.sources.sam_gov_api.httpx.AsyncClient",
        FakeClient,
    )

    asyncio.run(
        SamGovApiSource(
            api_key="test-key",
        ).fetch(limit=999)
    )

    assert captured["limit"] == "100"


def test_sam_source_wraps_http_failure_without_key(
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
        "app.sources.sam_gov_api.httpx.AsyncClient",
        FakeClient,
    )

    with pytest.raises(
        SourceError,
        match="Unable to fetch SAM.gov opportunities",
    ) as error:
        asyncio.run(
            SamGovApiSource(
                api_key="SUPER-SECRET-KEY",
            ).fetch()
        )

    assert "SUPER-SECRET-KEY" not in str(error.value)
