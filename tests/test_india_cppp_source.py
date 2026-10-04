import asyncio

import pytest

from app.sources.eis_rss import SourceError
from app.sources.india_cppp import (
    INDIA_CPPP_LIST_URL,
    IndiaCpppSource,
    parse_india_cppp_listing,
)


def _row(
    *,
    number: int = 1,
    published: str = "29-Sep-2026 01:00 PM",
    deadline: str = "05-Oct-2026 09:00 AM",
    opening: str = "06-Oct-2026 09:30 AM",
    title: str = (
        "ZLSS-8G-S Suspended Substrate "
        "Low Pass Filter"
    ),
    reference: str = (
        "TIFR/PD/SQ26-35/261364"
    ),
    tender_id: str = (
        "2026_DAE_928112_1"
    ),
    organisation: str = (
        "Department of Atomic Energy"
        "||Tata Institute of Fundamental Research"
    ),
) -> str:
    return f"""
<tr>
<td>
{number}. {published}
{deadline}
{opening}
[{title}]
[{reference}][{tender_id}]
{organisation}
<a href="/eprocure/app?component=%24DirectLink&amp;page=FrontEndListTendersbyDate&amp;service=direct&amp;session=T&amp;sp=Sabc">></a>
</td>
</tr>
"""


def _page(
    *rows: str,
    next_page: bool = False,
) -> bytes:
    next_html = ""

    if next_page:
        next_html = """
<a href="/eprocure/app?component=%24TablePages.linkFwd&amp;page=FrontEndListTendersbyDate&amp;service=direct&amp;session=T&amp;sp=AFrontEndListTendersbyDate%2Ctable&amp;sp=2">
Next
</a>
"""

    return (
        "<html><body>"
        + "".join(rows)
        + next_html
        + "</body></html>"
    ).encode("utf-8")


def test_parser_normalizes_cppp_tender() -> None:
    notices = parse_india_cppp_listing(
        _page(_row())
    )

    assert len(notices) == 1

    notice = notices[0]

    assert notice.source == "india_cppp"

    assert notice.external_id == (
        "2026_DAE_928112_1"
    )

    assert notice.tender_number == (
        "TIFR/PD/SQ26-35/261364"
    )

    assert notice.title == (
        "ZLSS-8G-S Suspended Substrate "
        "Low Pass Filter"
    )

    assert notice.customer == (
        "Department of Atomic Energy > "
        "Tata Institute of Fundamental Research"
    )

    assert notice.published_at == (
        "2026-09-29T13:00:00+05:30"
    )

    assert notice.deadline == (
        "2026-10-05T09:00:00+05:30"
    )

    assert notice.url == (
        INDIA_CPPP_LIST_URL
    )

    assert notice.initial_price is None
    assert notice.currency is None
    assert notice.region is None
    assert notice.summary is None


def test_parser_respects_limit() -> None:
    payload = _page(
        _row(
            number=1,
            tender_id="ID-1",
            reference="REF-1",
        ),
        _row(
            number=2,
            tender_id="ID-2",
            reference="REF-2",
        ),
        _row(
            number=3,
            tender_id="ID-3",
            reference="REF-3",
        ),
    )

    notices = parse_india_cppp_listing(
        payload,
        limit=2,
    )

    assert [
        notice.external_id
        for notice in notices
    ] == [
        "ID-1",
        "ID-2",
    ]


def test_parser_deduplicates_same_tender_id() -> None:
    row = _row(
        tender_id="ID-1",
        reference="REF-1",
    )

    notices = parse_india_cppp_listing(
        _page(
            row,
            row,
        )
    )

    assert len(notices) == 1
    assert notices[0].external_id == "ID-1"


def test_parser_rejects_conflicting_duplicate() -> None:
    payload = _page(
        _row(
            number=1,
            tender_id="ID-1",
            reference="REF-1",
            title="First title",
        ),
        _row(
            number=2,
            tender_id="ID-1",
            reference="REF-1",
            title="Changed title",
        ),
    )

    with pytest.raises(
        SourceError,
        match="conflicting duplicate",
    ):
        parse_india_cppp_listing(
            payload
        )


def test_parser_rejects_empty_page() -> None:
    with pytest.raises(
        SourceError,
        match="no tender rows",
    ):
        parse_india_cppp_listing(
            b"<html><body></body></html>"
        )


def test_parser_rejects_bad_date() -> None:
    with pytest.raises(
        SourceError,
        match="invalid Published Date",
    ):
        parse_india_cppp_listing(
            _page(
                _row(
                    published="32-Sep-2026 01:00 PM",
                )
            )
        )


def test_source_validates_timeout() -> None:
    with pytest.raises(
        ValueError,
        match="timeout",
    ):
        IndiaCpppSource(
            timeout=0,
        )


def test_source_fetches_multiple_pages_and_deduplicates(
    monkeypatch,
) -> None:
    first = _page(
        _row(
            number=1,
            tender_id="ID-1",
            reference="REF-1",
            title="Tender One",
        ),
        _row(
            number=2,
            tender_id="ID-2",
            reference="REF-2",
            title="Tender Two",
        ),
        next_page=True,
    )

    second = _page(
        _row(
            number=1,
            tender_id="ID-2",
            reference="REF-2",
            title="Tender Two",
        ),
        _row(
            number=2,
            tender_id="ID-3",
            reference="REF-3",
            title="Tender Three",
        ),
    )

    calls = []

    class FakeResponse:
        def __init__(
            self,
            content,
            url,
        ):
            self.content = content
            self.url = url

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(
            self,
            **kwargs,
        ):
            self.kwargs = kwargs

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
            calls.append(
                (
                    url,
                    kwargs,
                )
            )

            if len(calls) == 1:
                return FakeResponse(
                    first,
                    url,
                )

            return FakeResponse(
                second,
                url,
            )

    monkeypatch.setattr(
        "app.sources.india_cppp."
        "httpx.AsyncClient",
        FakeClient,
    )

    notices = asyncio.run(
        IndiaCpppSource().fetch(
            limit=3,
        )
    )

    assert [
        notice.external_id
        for notice in notices
    ] == [
        "ID-1",
        "ID-2",
        "ID-3",
    ]

    assert len(calls) == 2

    assert calls[0][0] == (
        INDIA_CPPP_LIST_URL
    )

    assert "Referer" in calls[1][1][
        "headers"
    ]


def test_source_stops_on_repeated_page_signature(
    monkeypatch,
) -> None:
    repeated = _page(
        _row(
            tender_id="ID-1",
            reference="REF-1",
        ),
        next_page=True,
    )

    calls = []

    class FakeResponse:
        def __init__(
            self,
            url,
        ):
            self.content = repeated
            self.url = url

        def raise_for_status(self):
            return None

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
            calls.append(url)

            return FakeResponse(
                url
            )

    monkeypatch.setattr(
        "app.sources.india_cppp."
        "httpx.AsyncClient",
        FakeClient,
    )

    notices = asyncio.run(
        IndiaCpppSource().fetch(
            limit=5,
        )
    )

    assert len(notices) == 1
    assert notices[0].external_id == "ID-1"

    assert len(calls) == 2


def test_source_wraps_http_failure(
    monkeypatch,
) -> None:
    import httpx

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
        "app.sources.india_cppp."
        "httpx.AsyncClient",
        FakeClient,
    )

    with pytest.raises(
        SourceError,
        match=(
            "Unable to fetch "
            "India CPPP tenders"
        ),
    ):
        asyncio.run(
            IndiaCpppSource().fetch()
        )