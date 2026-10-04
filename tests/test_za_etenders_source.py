import asyncio
import json

import httpx
import pytest

from app.sources.eis_rss import SourceError
from app.sources.za_etenders import (
    ZA_ETENDERS_ACTIVE_TENDERS_URL,
    ZA_ETENDERS_OPPORTUNITIES_URL,
    ZaETendersSource,
    parse_za_etenders_response,
)


def _row(
    *,
    tender_id: int = 172797,
    tender_no: str = "KZN ULM 12/26/27",
    description: str = (
        "EIGHT (8) MONTH CONTRACT - "
        "FULL YOUTH DRIVER'S LICENSE PROGRAM"
    ),
    department: str = "uMlalazi Municipality",
    published: str = "2026-10-04T00:00:00",
    closing: str = "2026-11-03T12:00:00",
    province: str | None = "KwaZulu-Natal",
    category: str | None = "Services: General",
    tender_type: str | None = "Request for Bid(Open-Tender)",
    conditions: str | None = (
        "Service Providers with registered "
        "driving schools to submit tenders."
    ),
    delivery: str | None = (
        "11 KV CHALLENOR STREET - "
        "ESHOWE - ESHOWE - 3815"
    ),
) -> dict:
    return {
        "id": tender_id,
        "tender_No": tender_no,
        "description": description,
        "department": department,
        "date_Published": published,
        "closing_Date": closing,
        "province": province,
        "category": category,
        "type": tender_type,
        "conditions": conditions,
        "delivery": delivery,
        "status": "Published",
    }


def _payload(*rows: dict) -> bytes:
    return json.dumps(
        list(rows),
        ensure_ascii=False,
    ).encode("utf-8")


def test_parser_normalizes_active_tender() -> None:
    notices = parse_za_etenders_response(
        _payload(_row())
    )

    assert len(notices) == 1

    notice = notices[0]

    assert notice.source == "za_etenders"
    assert notice.external_id == "172797"
    assert notice.tender_number == (
        "KZN ULM 12/26/27"
    )

    assert notice.title == (
        "EIGHT (8) MONTH CONTRACT - "
        "FULL YOUTH DRIVER'S LICENSE PROGRAM"
    )

    assert notice.customer == (
        "uMlalazi Municipality"
    )

    assert notice.published_at == (
        "2026-10-04T00:00:00+02:00"
    )

    assert notice.deadline == (
        "2026-11-03T12:00:00+02:00"
    )

    assert notice.region == (
        "KwaZulu-Natal"
    )

    assert notice.url == (
        ZA_ETENDERS_OPPORTUNITIES_URL
    )

    assert notice.initial_price is None
    assert notice.currency is None

    assert notice.summary == (
        "Tender type: Request for Bid(Open-Tender). "
        "Category: Services: General. "
        "Special conditions: Service Providers with "
        "registered driving schools to submit tenders. "
        "Delivery: 11 KV CHALLENOR STREET - "
        "ESHOWE - ESHOWE - 3815"
    )


def test_parser_sorts_before_limit() -> None:
    payload = _payload(
        _row(
            tender_id=100,
            tender_no="OLD",
            published="2026-10-01T00:00:00",
        ),
        _row(
            tender_id=300,
            tender_no="NEW",
            published="2026-10-04T00:00:00",
        ),
        _row(
            tender_id=200,
            tender_no="MIDDLE",
            published="2026-10-03T00:00:00",
        ),
    )

    notices = parse_za_etenders_response(
        payload,
        limit=2,
    )

    assert [
        notice.external_id
        for notice in notices
    ] == [
        "300",
        "200",
    ]


def test_parser_deduplicates_by_portal_id() -> None:
    payload = _payload(
        _row(
            tender_id=500,
            tender_no="FIRST",
        ),
        _row(
            tender_id=500,
            tender_no="SECOND",
        ),
    )

    notices = parse_za_etenders_response(
        payload
    )

    assert len(notices) == 1
    assert notices[0].external_id == "500"
    assert notices[0].tender_number == "FIRST"


def test_parser_allows_optional_summary_fields() -> None:
    notice = parse_za_etenders_response(
        _payload(
            _row(
                province="N/A",
                category="N/A",
                tender_type=None,
                conditions="<not available>",
                delivery=None,
            )
        )
    )[0]

    assert notice.region is None
    assert notice.summary is None


def test_parser_rejects_invalid_json() -> None:
    with pytest.raises(
        SourceError,
        match="invalid JSON",
    ):
        parse_za_etenders_response(
            b"{broken"
        )


def test_parser_rejects_unexpected_structure() -> None:
    with pytest.raises(
        SourceError,
        match="unexpected JSON structure",
    ):
        parse_za_etenders_response(
            b'{"items": []}'
        )


def test_parser_rejects_missing_required_field() -> None:
    row = _row()
    row["tender_No"] = " "

    with pytest.raises(
        SourceError,
        match="without tender_No",
    ):
        parse_za_etenders_response(
            _payload(row)
        )


def test_source_validates_timeout() -> None:
    with pytest.raises(
        ValueError,
        match="timeout",
    ):
        ZaETendersSource(
            timeout=0,
        )


def test_source_fetches_active_opportunities(
    monkeypatch,
) -> None:
    captured = {}

    payload = _payload(
        _row()
    )

    class FakeResponse:
        content = payload

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(
            self,
            **kwargs,
        ):
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

        async def get(
            self,
            url,
            **kwargs,
        ):
            captured["url"] = url
            captured["get_kwargs"] = kwargs
            return FakeResponse()

    monkeypatch.setattr(
        "app.sources.za_etenders."
        "httpx.AsyncClient",
        FakeClient,
    )

    notices = asyncio.run(
        ZaETendersSource().fetch(
            limit=5,
        )
    )

    assert len(notices) == 1

    assert captured["url"] == (
        ZA_ETENDERS_ACTIVE_TENDERS_URL
    )

    assert captured[
        "get_kwargs"
    ]["params"] == {
        "status": 1,
    }

    headers = captured[
        "client_kwargs"
    ]["headers"]

    assert headers[
        "Referer"
    ] == ZA_ETENDERS_OPPORTUNITIES_URL

    assert headers[
        "User-Agent"
    ].startswith(
        "Mozilla/5.0"
    )


def test_source_wraps_http_failure(
    monkeypatch,
) -> None:
    class FakeClient:
        def __init__(
            self,
            **kwargs,
        ):
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

        async def get(
            self,
            url,
            **kwargs,
        ):
            raise httpx.ConnectError(
                "offline"
            )

    monkeypatch.setattr(
        "app.sources.za_etenders."
        "httpx.AsyncClient",
        FakeClient,
    )

    with pytest.raises(
        SourceError,
        match=(
            "Unable to fetch South Africa "
            "eTenders opportunities"
        ),
    ):
        asyncio.run(
            ZaETendersSource().fetch()
        )