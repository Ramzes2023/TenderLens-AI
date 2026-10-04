import asyncio

import httpx
import pytest

from app.sources.austender_rss import (
    AUSTENDER_ATM_BASE_URL,
    AUSTENDER_RSS_URL,
    AusTenderRssSource,
    parse_austender_detail_page,
    parse_austender_rss,
)
from app.sources.eis_rss import SourceError


UUID_1 = "8daeb3c8-8323-4fbd-86d1-0a7adbf18d63"
UUID_2 = "bcd79820-adc0-4f22-b8ad-6c9058cc1f68"


def _rss_bytes() -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>
        6212-2025-26: ISO 9001 Certification Services
      </title>
      <link>{AUSTENDER_ATM_BASE_URL}{UUID_1}</link>
      <guid>{AUSTENDER_ATM_BASE_URL}{UUID_1}</guid>
      <pubDate>Thu, 24 Sep 2026 00:00:00 GMT</pubDate>
    </item>

    <item>
      <title>Duplicate ATM record</title>
      <link>{AUSTENDER_ATM_BASE_URL}{UUID_1}</link>
      <guid>{AUSTENDER_ATM_BASE_URL}{UUID_1}</guid>
      <pubDate>Thu, 24 Sep 2026 00:00:00 GMT</pubDate>
    </item>

    <item>
      <title>Second ATM</title>
      <link>{AUSTENDER_ATM_BASE_URL}{UUID_2}</link>
      <guid>{AUSTENDER_ATM_BASE_URL}{UUID_2}</guid>
      <pubDate>Thu, 10 Sep 2026 00:00:00 GMT</pubDate>
    </item>

    <item>
      <title>PROC-123: Advert record</title>
      <link>
        https://www.tenders.gov.au/Advert/Show/
        66f4a310-94b0-4ea0-8f79-76805211c961
      </link>
      <guid>
        https://www.tenders.gov.au/Advert/Show/
        66f4a310-94b0-4ea0-8f79-76805211c961
      </guid>
    </item>
  </channel>
</rss>
""".encode("utf-8")


def _detail_html(
    *,
    estimated_value: str = (
        "From $20,000.00 to $25,000.00"
    ),
) -> str:
    return f"""
<html>
<head>
<script>
dataLayer.push({{
    'atmTitle':
        'ISO 9001 Certification Services – Tsunami Warning Services',
    'atmID': '6212-2025-26',
    'atmAgencyName': 'Bureau of Meteorology',
    'atmCategoryCode': '80100000',
    'atmCategoryTitle': 'Management advisory services',
    'atmType': 'Request for Quote',
    'atmLocationState': 'VIC',
    'atmLocationCity': 'Melbourne'
}});
</script>
</head>
<body>

<div class="list-desc">
  <span><label for="AtmId">ATM ID</label>:</span>
  <div class="list-desc-inner">6212-2025-26</div>
</div>

<div class="list-desc">
  <span><label for="Agency">Agency</label>:</span>
  <div class="list-desc-inner">Bureau of Meteorology</div>
</div>

<div class="list-desc">
  <span><label for="Category">Category</label>:</span>
  <div class="list-desc-inner">
    80100000 - Management advisory services
  </div>
</div>

<div class="list-desc">
  <span><label for="CloseDate">Close Date &amp; Time</label>:</span>
  <div class="list-desc-inner">
    5-Oct-2026 12:00 pm
    <span>(ACT Local Time)</span>
    <br>
    <a
      href="/TimeZone?CloseDateTime=10%2F05%2F2026%2012%3A00%3A00"
      id="timeZoneLink"
    >
      Show close time for other time zones
    </a>
  </div>
</div>

<div class="list-desc">
  <span><label for="PublishDate">Publish Date</label>:</span>
  <div class="list-desc-inner">24-Sep-2026</div>
</div>

<div class="list-desc">
  <span><label for="Locations">Location</label>:</span>
  <div class="list-desc-inner">
    VIC<br />Melbourne
  </div>
</div>

<div class="list-desc">
  <span><label for="Description">Description</label>:</span>
  <div class="list-desc-inner">
    <p>Refer to Statement of Requirements</p>
  </div>
</div>

<div class="list-desc">
  <span>Estimated Value (AUD):</span>
  <div class="list-desc-inner">
    {estimated_value}
  </div>
</div>

</body>
</html>
"""


def test_rss_parser_filters_adverts_and_deduplicates() -> None:
    items = parse_austender_rss(
        _rss_bytes()
    )

    assert len(items) == 2

    assert items[0].external_id == UUID_1
    assert items[0].published_at == "2026-09-24"
    assert items[0].url == (
        AUSTENDER_ATM_BASE_URL + UUID_1
    )

    assert items[1].external_id == UUID_2

    assert all(
        "/Atm/Show/" in item.url
        for item in items
    )


def test_rss_parser_rejects_invalid_xml() -> None:
    with pytest.raises(
        SourceError,
        match="invalid RSS XML",
    ):
        parse_austender_rss(
            b"<rss><broken>"
        )


def test_detail_parser_normalizes_realistic_atm() -> None:
    notice = parse_austender_detail_page(
        _detail_html(),
        external_id=UUID_1,
        url=AUSTENDER_ATM_BASE_URL + UUID_1,
        rss_title=(
            "6212-2025-26: "
            "ISO 9001 Certification Services – "
            "Tsunami Warning Services"
        ),
        rss_published_at="2026-09-24",
    )

    assert notice.source == "austender"
    assert notice.external_id == UUID_1

    assert notice.tender_number == (
        "6212-2025-26"
    )

    assert notice.title == (
        "ISO 9001 Certification Services – "
        "Tsunami Warning Services"
    )

    assert notice.customer == (
        "Bureau of Meteorology"
    )

    assert notice.published_at == (
        "2026-09-24"
    )

    assert notice.deadline == (
        "2026-10-05T12:00:00"
    )

    assert notice.region == (
        "VIC, Melbourne"
    )

    assert notice.summary == (
        "Refer to Statement of Requirements"
    )

    # TenderNotice has only one price field.
    # Do not collapse an official min/max range.
    assert notice.initial_price is None
    assert notice.currency == "AUD"

    assert notice.url == (
        AUSTENDER_ATM_BASE_URL + UUID_1
    )


def test_detail_parser_accepts_exact_estimated_value() -> None:
    notice = parse_austender_detail_page(
        _detail_html(
            estimated_value="$50,000.00"
        ),
        external_id=UUID_1,
        url=AUSTENDER_ATM_BASE_URL + UUID_1,
        rss_title="Example ATM",
    )

    assert notice.initial_price == 50000.0
    assert notice.currency == "AUD"


def test_source_validates_configuration() -> None:
    with pytest.raises(
        ValueError,
        match="timeout",
    ):
        AusTenderRssSource(
            timeout=0,
        )

    with pytest.raises(
        ValueError,
        match="max_concurrency",
    ):
        AusTenderRssSource(
            max_concurrency=0,
        )

    with pytest.raises(
        ValueError,
        match="max_concurrency",
    ):
        AusTenderRssSource(
            max_concurrency=21,
        )


def test_source_fetches_rss_and_detail_pages(
    monkeypatch,
) -> None:
    captured = {
        "urls": [],
    }

    rss_payload = _rss_bytes()

    detail_payload = (
        _detail_html().encode("utf-8")
    )

    class FakeResponse:
        def __init__(
            self,
            content: bytes,
        ) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(
            self,
            **kwargs,
        ) -> None:
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
            captured["urls"].append(url)

            if url == AUSTENDER_RSS_URL:
                return FakeResponse(
                    rss_payload
                )

            if url == (
                AUSTENDER_ATM_BASE_URL
                + UUID_1
            ):
                return FakeResponse(
                    detail_payload
                )

            raise AssertionError(
                f"Unexpected URL: {url}"
            )

    monkeypatch.setattr(
        "app.sources.austender_rss."
        "httpx.AsyncClient",
        FakeClient,
    )

    notices = asyncio.run(
        AusTenderRssSource(
            max_concurrency=2,
        ).fetch(
            limit=1,
        )
    )

    assert len(notices) == 1

    assert notices[0].external_id == UUID_1

    assert captured["urls"] == [
        AUSTENDER_RSS_URL,
        AUSTENDER_ATM_BASE_URL + UUID_1,
    ]

    headers = (
        captured[
            "client_kwargs"
        ]["headers"]
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
        ) -> None:
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
        "app.sources.austender_rss."
        "httpx.AsyncClient",
        FakeClient,
    )

    with pytest.raises(
        SourceError,
        match=(
            "Unable to fetch AusTender notices"
        ),
    ):
        asyncio.run(
            AusTenderRssSource().fetch()
        )