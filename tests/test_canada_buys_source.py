import asyncio
import csv
import io

import httpx
import pytest

from app.sources import (
    CANADABUYS_OPEN_TENDERS_URL,
    CanadaBuysDatasetSource,
    parse_canadabuys_csv,
)
from app.sources.eis_rss import SourceError


HEADERS = [
    "title-titre-eng",
    "title-titre-fra",
    "referenceNumber-numeroReference",
    "amendmentNumber-numeroModification",
    "solicitationNumber-numeroSollicitation",
    "publicationDate-datePublication",
    "tenderClosingDate-appelOffresDateCloture",
    "amendmentDate-dateModification",
    "tenderStatus-appelOffresStatut-eng",
    "regionsOfOpportunity-regionAppelOffres-eng",
    "regionsOfOpportunity-regionAppelOffres-fra",
    "regionsOfDelivery-regionsLivraison-eng",
    "regionsOfDelivery-regionsLivraison-fra",
    "contractingEntityName-nomEntitContractante-eng",
    "contractingEntityName-nomEntitContractante-fra",
    "noticeURL-URLavis-eng",
    "noticeURL-URLavis-fra",
    "tenderDescription-descriptionAppelOffres-eng",
    "tenderDescription-descriptionAppelOffres-fra",
]


def _csv_bytes(rows):
    stream = io.StringIO()

    writer = csv.DictWriter(
        stream,
        fieldnames=HEADERS,
        lineterminator="\n",
    )

    writer.writeheader()

    for row in rows:
        writer.writerow(row)

    return stream.getvalue().encode("utf-8")


def test_parse_canadabuys_normalizes_notice() -> None:
    payload = _csv_bytes([
        {
            "title-titre-eng": (
                "Open Construction Source List for CFB Halifax"
            ),
            "referenceNumber-numeroReference": (
                "MX-443841357513"
            ),
            "amendmentNumber-numeroModification": "001",
            "solicitationNumber-numeroSollicitation": (
                "AR26SLHX_86026"
            ),
            "publicationDate-datePublication": "2026-01-23",
            "tenderClosingDate-appelOffresDateCloture": (
                "2029-03-31T13:00:00"
            ),
            "amendmentDate-dateModification": "2026-02-01",
            "tenderStatus-appelOffresStatut-eng": "Open",
            "regionsOfDelivery-regionsLivraison-eng": (
                "Nova Scotia"
            ),
            "contractingEntityName-nomEntitContractante-eng": (
                "Defence Construction Canada - Atlantic Region"
            ),
            "noticeURL-URLavis-eng": (
                "https://www.merx.com/public/"
                "solicitations/3776296409/abstract?language=EN"
            ),
            "tenderDescription-descriptionAppelOffres-eng": (
                "Commercial &amp; civil work.<br/>"
                "Open source list."
            ),
        }
    ])

    notices = parse_canadabuys_csv(
        payload,
        limit=20,
    )

    assert len(notices) == 1

    notice = notices[0]

    assert notice.source == "canada_buys"
    assert notice.external_id == "MX-443841357513"
    assert notice.tender_number == "AR26SLHX_86026"
    assert notice.title == (
        "Open Construction Source List for CFB Halifax"
    )
    assert notice.published_at == "2026-01-23"
    assert notice.deadline == "2029-03-31T13:00:00"
    assert notice.customer == (
        "Defence Construction Canada - Atlantic Region"
    )
    assert notice.region == "Nova Scotia"
    assert notice.initial_price is None
    assert notice.currency is None
    assert notice.summary == (
        "Commercial & civil work. Open source list."
    )
    assert notice.url.startswith(
        "https://www.merx.com/"
    )


def test_reference_number_is_identity_not_amendment() -> None:
    payload = _csv_bytes([
        {
            "title-titre-eng": "Updated tender",
            "referenceNumber-numeroReference": "REF-100",
            "amendmentNumber-numeroModification": "019",
            "solicitationNumber-numeroSollicitation": "SOL-100",
            "publicationDate-datePublication": "2026-01-01",
            "tenderClosingDate-appelOffresDateCloture": (
                "2026-12-31"
            ),
        }
    ])

    notice = parse_canadabuys_csv(payload)[0]

    assert notice.external_id == "REF-100"
    assert notice.tender_number == "SOL-100"


def test_parser_uses_search_fallback_when_url_missing() -> None:
    payload = _csv_bytes([
        {
            "title-titre-eng": "Tender without direct URL",
            "referenceNumber-numeroReference": "REF-200",
            "solicitationNumber-numeroSollicitation": "SOL-200",
            "publicationDate-datePublication": "2026-02-01",
            "tenderClosingDate-appelOffresDateCloture": (
                "2026-03-01"
            ),
        }
    ])

    notice = parse_canadabuys_csv(payload)[0]

    assert notice.url.startswith(
        "https://canadabuys.canada.ca/"
        "en/tender-opportunities?"
    )
    assert "SOL-200" in notice.url


def test_parser_rejects_missing_required_schema() -> None:
    payload = (
        "referenceNumber-numeroReference,title-titre-eng\n"
        "REF-1,Example\n"
    ).encode("utf-8")

    with pytest.raises(
        SourceError,
        match="schema is missing required fields",
    ):
        parse_canadabuys_csv(payload)


def test_parser_orders_by_latest_activity_before_limit() -> None:
    payload = _csv_bytes([
        {
            "title-titre-eng": "Older",
            "referenceNumber-numeroReference": "REF-OLD",
            "solicitationNumber-numeroSollicitation": "SOL-OLD",
            "publicationDate-datePublication": "2026-01-01",
            "tenderClosingDate-appelOffresDateCloture": (
                "2026-12-01"
            ),
            "amendmentDate-dateModification": "2026-01-02",
        },
        {
            "title-titre-eng": "Newer amendment",
            "referenceNumber-numeroReference": "REF-NEW",
            "solicitationNumber-numeroSollicitation": "SOL-NEW",
            "publicationDate-datePublication": "2026-01-01",
            "tenderClosingDate-appelOffresDateCloture": (
                "2026-12-01"
            ),
            "amendmentDate-dateModification": "2026-10-01",
        },
    ])

    notices = parse_canadabuys_csv(
        payload,
        limit=1,
    )

    assert len(notices) == 1
    assert notices[0].external_id == "REF-NEW"


def test_parser_deduplicates_reference_number() -> None:
    payload = _csv_bytes([
        {
            "title-titre-eng": "Newest",
            "referenceNumber-numeroReference": "REF-DUP",
            "solicitationNumber-numeroSollicitation": "SOL-DUP",
            "publicationDate-datePublication": "2026-01-01",
            "tenderClosingDate-appelOffresDateCloture": (
                "2026-12-01"
            ),
            "amendmentDate-dateModification": "2026-10-01",
        },
        {
            "title-titre-eng": "Older",
            "referenceNumber-numeroReference": "REF-DUP",
            "solicitationNumber-numeroSollicitation": "SOL-DUP",
            "publicationDate-datePublication": "2026-01-01",
            "tenderClosingDate-appelOffresDateCloture": (
                "2026-12-01"
            ),
            "amendmentDate-dateModification": "2026-02-01",
        },
    ])

    notices = parse_canadabuys_csv(payload)

    assert len(notices) == 1
    assert notices[0].title == "Newest"


def test_source_validates_timeout() -> None:
    with pytest.raises(
        ValueError,
        match="timeout",
    ):
        CanadaBuysDatasetSource(timeout=0)


def test_source_fetches_official_dataset(
    monkeypatch,
) -> None:
    captured = {}

    payload = _csv_bytes([
        {
            "title-titre-eng": "Example tender",
            "referenceNumber-numeroReference": "REF-300",
            "solicitationNumber-numeroSollicitation": "SOL-300",
            "publicationDate-datePublication": "2026-03-01",
            "tenderClosingDate-appelOffresDateCloture": (
                "2026-04-01"
            ),
        }
    ])

    class FakeResponse:
        content = payload

        def raise_for_status(self) -> None:
            return None

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
        "app.sources.canada_buys_dataset.httpx.AsyncClient",
        FakeClient,
    )

    result = asyncio.run(
        CanadaBuysDatasetSource().fetch(limit=5)
    )

    assert len(result) == 1
    assert captured["url"] == CANADABUYS_OPEN_TENDERS_URL


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

        async def get(self, url):
            raise httpx.ConnectError("offline")

    monkeypatch.setattr(
        "app.sources.canada_buys_dataset.httpx.AsyncClient",
        FakeClient,
    )

    with pytest.raises(
        SourceError,
        match="Unable to fetch CanadaBuys open tender dataset",
    ):
        asyncio.run(
            CanadaBuysDatasetSource().fetch()
        )
