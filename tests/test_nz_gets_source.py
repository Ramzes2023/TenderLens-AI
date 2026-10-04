import asyncio

import httpx
import pytest

from app.sources.eis_rss import SourceError
from app.sources.nz_gets_rss import (
    NZ_GETS_RSS_URL,
    NzGetsRssSource,
    parse_nz_gets_rss,
)


def _item(
    *,
    rfx_id: str,
    title: str,
    organisation: str = "Example Agency",
    pub_date: str,
    open_date: str,
    close_date: str,
    region: str | None = "New Zealand",
    overview: str | None = "Example procurement overview.",
    agency_path: str = "TEST",
    guid_id: str | None = None,
) -> str:
    link = (
        "https://www.gets.govt.nz//"
        f"{agency_path}/ExternalTenderDetails.htm"
        f"?id={rfx_id}"
    )

    guid = (
        "https://www.gets.govt.nz//"
        f"{agency_path}/ExternalTenderDetails.htm"
        f"?id={guid_id or rfx_id}"
    )

    region_row = (
        "<tr>"
        "<td valign='top'><b>Region: </b></td>"
        f"<td>{region}</td>"
        "</tr>"
        if region is not None
        else ""
    )

    overview_row = (
        "<tr>"
        "<td valign='top'><b>Overview: </b></td>"
        f"<td>{overview}</td>"
        "</tr>"
        if overview is not None
        else ""
    )

    description = f"""
<table>
<tr>
<td><b>RFx ID: </b></td>
<td>{rfx_id}</td>
</tr>
<tr>
<td><b>Organisation: </b></td>
<td>{organisation}</td>
</tr>
<tr>
<td><b>Open date: </b></td>
<td>{open_date}</td>
</tr>
<tr>
<td><b>Close date: </td>
<td>{close_date}</td>
</tr>
{region_row}
{overview_row}
</table>
"""

    return f"""
<item>
<title>{title}</title>
<link>{link}</link>
<guid>{guid}</guid>
<pubDate>{pub_date}</pubDate>
<description><![CDATA[{description}]]></description>
</item>
"""


def _rss(*items: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<rss version="2.0">'
        '<channel>'
        + "".join(items)
        + '</channel>'
        '</rss>'
    ).encode("utf-8")


def test_parser_normalizes_gets_notice() -> None:
    payload = _rss(
        _item(
            rfx_id="35070355",
            title=(
                "Main Contractor for Fire Alarm "
                "&amp; Roofing Works"
            ),
            organisation=(
                "Ministry of Education - School Infrastructure"
            ),
            pub_date=(
                "Sun, 04 Oct 2026 17:00:00 GMT"
            ),
            open_date=(
                "Monday, 5 October 2026 "
                "6:00 AM +13:00"
            ),
            close_date=(
                "Wednesday, 4 November 2026 "
                "5:00 PM +13:00"
            ),
            region="Northland",
            overview=(
                "Fire alarm replacement.<br>"
                "Roofing replacement works."
            ),
            agency_path="MEDUR",
        )
    )

    notices = parse_nz_gets_rss(
        payload,
        limit=20,
    )

    assert len(notices) == 1

    notice = notices[0]

    assert notice.source == "nz_gets"
    assert notice.external_id == "35070355"
    assert notice.tender_number == "35070355"

    assert notice.title == (
        "Main Contractor for Fire Alarm & Roofing Works"
    )

    assert notice.customer == (
        "Ministry of Education - School Infrastructure"
    )

    assert notice.published_at == (
        "2026-10-04T17:00:00+00:00"
    )

    assert notice.deadline == (
        "2026-11-04T17:00:00+13:00"
    )

    assert notice.region == "Northland"

    assert notice.summary == (
        "Fire alarm replacement. "
        "Roofing replacement works."
    )

    assert notice.initial_price is None
    assert notice.currency is None

    assert notice.url == (
        "https://www.gets.govt.nz/"
        "MEDUR/ExternalTenderDetails.htm"
        "?id=35070355"
    )


def test_parser_sorts_by_publication_before_limit() -> None:
    payload = _rss(
        _item(
            rfx_id="100",
            title="Oldest",
            pub_date=(
                "Thu, 01 Oct 2026 01:00:00 GMT"
            ),
            open_date=(
                "Thursday, 1 October 2026 "
                "2:00 PM +13:00"
            ),
            close_date=(
                "Thursday, 31 December 2026 "
                "5:00 PM +13:00"
            ),
        ),
        _item(
            rfx_id="300",
            title="Newest",
            pub_date=(
                "Sun, 04 Oct 2026 17:00:00 GMT"
            ),
            open_date=(
                "Monday, 5 October 2026 "
                "6:00 AM +13:00"
            ),
            close_date=(
                "Friday, 30 October 2026 "
                "5:00 PM +13:00"
            ),
        ),
        _item(
            rfx_id="200",
            title="Middle",
            pub_date=(
                "Fri, 02 Oct 2026 03:00:00 GMT"
            ),
            open_date=(
                "Friday, 2 October 2026 "
                "4:00 PM +13:00"
            ),
            close_date=(
                "Friday, 6 November 2026 "
                "5:00 PM +13:00"
            ),
        ),
    )

    notices = parse_nz_gets_rss(
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


def test_parser_allows_missing_region_and_overview() -> None:
    payload = _rss(
        _item(
            rfx_id="500",
            title="Nullable fields",
            pub_date=(
                "Fri, 02 Oct 2026 01:00:00 GMT"
            ),
            open_date=(
                "Friday, 2 October 2026 "
                "2:00 PM +13:00"
            ),
            close_date=(
                "Friday, 30 October 2026 "
                "5:00 PM +13:00"
            ),
            region=None,
            overview=None,
        )
    )

    notice = parse_nz_gets_rss(
        payload
    )[0]

    assert notice.region is None
    assert notice.summary is None


def test_parser_rejects_link_guid_mismatch() -> None:
    payload = _rss(
        _item(
            rfx_id="600",
            guid_id="601",
            title="Mismatch",
            pub_date=(
                "Fri, 02 Oct 2026 01:00:00 GMT"
            ),
            open_date=(
                "Friday, 2 October 2026 "
                "2:00 PM +13:00"
            ),
            close_date=(
                "Friday, 30 October 2026 "
                "5:00 PM +13:00"
            ),
        )
    )

    with pytest.raises(
        SourceError,
        match="mismatched link and guid",
    ):
        parse_nz_gets_rss(
            payload
        )


def test_parser_rejects_rfx_id_mismatch() -> None:
    payload = _rss(
        """
<item>
<title>RFx mismatch</title>
<link>
https://www.gets.govt.nz//TEST/ExternalTenderDetails.htm?id=700
</link>
<guid>
https://www.gets.govt.nz//TEST/ExternalTenderDetails.htm?id=700
</guid>
<pubDate>Fri, 02 Oct 2026 01:00:00 GMT</pubDate>
<description><![CDATA[
<table>
<tr><td><b>RFx ID: </b></td><td>701</td></tr>
<tr><td><b>Organisation: </b></td><td>Agency</td></tr>
<tr>
<td><b>Open date: </b></td>
<td>Friday, 2 October 2026 2:00 PM +13:00</td>
</tr>
<tr>
<td><b>Close date: </td>
<td>Friday, 30 October 2026 5:00 PM +13:00</td>
</tr>
</table>
]]></description>
</item>
"""
    )

    with pytest.raises(
        SourceError,
        match="RFx ID does not match",
    ):
        parse_nz_gets_rss(
            payload
        )


def test_parser_rejects_invalid_xml() -> None:
    with pytest.raises(
        SourceError,
        match="invalid RSS XML",
    ):
        parse_nz_gets_rss(
            b"<rss><broken>"
        )


def test_source_validates_timeout() -> None:
    with pytest.raises(
        ValueError,
        match="timeout",
    ):
        NzGetsRssSource(
            timeout=0,
        )


def test_source_fetches_official_rss(
    monkeypatch,
) -> None:
    captured = {}

    payload = _rss(
        _item(
            rfx_id="800",
            title="Fetched tender",
            pub_date=(
                "Sun, 04 Oct 2026 17:00:00 GMT"
            ),
            open_date=(
                "Monday, 5 October 2026 "
                "6:00 AM +13:00"
            ),
            close_date=(
                "Wednesday, 4 November 2026 "
                "5:00 PM +13:00"
            ),
        )
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
        ):
            captured["url"] = url
            return FakeResponse()

    monkeypatch.setattr(
        "app.sources.nz_gets_rss."
        "httpx.AsyncClient",
        FakeClient,
    )

    notices = asyncio.run(
        NzGetsRssSource().fetch(
            limit=5,
        )
    )

    assert len(notices) == 1
    assert notices[0].external_id == "800"

    assert captured["url"] == (
        NZ_GETS_RSS_URL
    )

    headers = (
        captured["client_kwargs"][
            "headers"
        ]
    )

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
        ):
            raise httpx.ConnectError(
                "offline"
            )

    monkeypatch.setattr(
        "app.sources.nz_gets_rss."
        "httpx.AsyncClient",
        FakeClient,
    )

    with pytest.raises(
        SourceError,
        match="Unable to fetch GETS notices",
    ):
        asyncio.run(
            NzGetsRssSource().fetch()
        )