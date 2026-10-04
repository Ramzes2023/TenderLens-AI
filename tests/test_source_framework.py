import asyncio
from dataclasses import dataclass, field

import pytest

from app.sources import (
    MultiSourceFetcher,
    SourceRegistration,
    SourceRegistry,
    SourceRegistryError,
    TenderNotice,
)


@dataclass
class FakeSource:
    name: str
    notices: list[TenderNotice] = field(default_factory=list)
    error: Exception | None = None
    calls: int = 0

    async def fetch(self, limit: int = 20) -> list[TenderNotice]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.notices[:limit]


def notice(source: str, external_id: str) -> TenderNotice:
    return TenderNotice(
        source=source,
        external_id=external_id,
        title=f"Tender {external_id}",
        url=f"https://example.test/{source}/{external_id}",
    )


def test_registry_rejects_duplicate_source() -> None:
    source = FakeSource("ted")
    registration = SourceRegistration(
        key="ted",
        display_name="TED",
        source=source,
    )
    registry = SourceRegistry([registration])

    with pytest.raises(SourceRegistryError):
        registry.register(registration)


def test_registry_rejects_adapter_name_mismatch() -> None:
    with pytest.raises(SourceRegistryError):
        SourceRegistration(
            key="ted",
            display_name="TED",
            source=FakeSource("sam"),
        )


def test_multi_source_fetch_merges_and_deduplicates() -> None:
    ted = FakeSource(
        "ted",
        [
            notice("ted", "1"),
            notice("ted", "1"),
            notice("ted", "2"),
        ],
    )
    sam = FakeSource(
        "sam",
        [notice("sam", "A")],
    )

    registry = SourceRegistry(
        [
            SourceRegistration("ted", "TED", ted),
            SourceRegistration("sam", "SAM.gov", sam),
        ]
    )

    report = asyncio.run(
        MultiSourceFetcher(registry).fetch(limit_per_source=20)
    )

    assert [item.identity for item in report.notices] == [
        ("ted", "1"),
        ("ted", "2"),
        ("sam", "A"),
    ]
    assert report.failures == ()
    assert report.attempted_sources == ("ted", "sam")
    assert report.successful_sources == ("ted", "sam")


def test_multi_source_fetch_isolates_failed_source() -> None:
    ted = FakeSource(
        "ted",
        [notice("ted", "1")],
    )
    sam = FakeSource(
        "sam",
        error=RuntimeError("temporary upstream failure"),
    )

    registry = SourceRegistry(
        [
            SourceRegistration("ted", "TED", ted),
            SourceRegistration("sam", "SAM.gov", sam),
        ]
    )

    report = asyncio.run(MultiSourceFetcher(registry).fetch())

    assert [item.identity for item in report.notices] == [("ted", "1")]
    assert report.successful_sources == ("ted",)
    assert report.partial_failure is True
    assert report.total_failure is False
    assert len(report.failures) == 1
    assert report.failures[0].source == "sam"
    assert report.failures[0].error_type == "RuntimeError"


def test_disabled_source_is_not_fetched_by_default() -> None:
    ted = FakeSource("ted", [notice("ted", "1")])
    disabled = FakeSource("sam", [notice("sam", "A")])

    registry = SourceRegistry(
        [
            SourceRegistration("ted", "TED", ted),
            SourceRegistration(
                "sam",
                "SAM.gov",
                disabled,
                enabled=False,
            ),
        ]
    )

    report = asyncio.run(MultiSourceFetcher(registry).fetch())

    assert report.attempted_sources == ("ted",)
    assert ted.calls == 1
    assert disabled.calls == 0


def test_contract_violation_is_reported_as_source_failure() -> None:
    broken = FakeSource(
        "ted",
        [notice("wrong-source", "1")],
    )
    registry = SourceRegistry(
        [SourceRegistration("ted", "TED", broken)]
    )

    report = asyncio.run(MultiSourceFetcher(registry).fetch())

    assert report.notices == ()
    assert report.total_failure is True
    assert report.failures[0].source == "ted"
    assert report.failures[0].error_type == "ValueError"

def test_registry_exposes_safe_source_metadata() -> None:
    from app.sources import SourceCapabilities, SourceTransport

    source = FakeSource("ted")

    registry = SourceRegistry(
        [
            SourceRegistration(
                key="ted",
                display_name="Tenders Electronic Daily",
                source=source,
                transport=SourceTransport.API,
                jurisdictions=("EU",),
                languages=("en", "fr"),
                homepage_url="https://ted.europa.eu/",
                official=True,
                capabilities=SourceCapabilities(
                    keyword_search=True,
                    pagination=True,
                    documents=True,
                ),
            )
        ]
    )

    metadata = registry.metadata()[0]

    assert metadata.key == "ted"
    assert metadata.display_name == "Tenders Electronic Daily"
    assert metadata.transport == SourceTransport.API
    assert metadata.jurisdictions == ("EU",)
    assert metadata.languages == ("en", "fr")
    assert metadata.homepage_url == "https://ted.europa.eu/"
    assert metadata.official is True
    assert metadata.capabilities.keyword_search is True
    assert metadata.capabilities.documents is True


def test_registry_rejects_insecure_homepage() -> None:
    with pytest.raises(SourceRegistryError):
        SourceRegistration(
            key="ted",
            display_name="TED",
            source=FakeSource("ted"),
            homepage_url="http://ted.example.test/",
        )


def test_registry_rejects_invalid_language_code() -> None:
    with pytest.raises(SourceRegistryError):
        SourceRegistration(
            key="ted",
            display_name="TED",
            source=FakeSource("ted"),
            languages=("english",),
        )


def test_fetch_report_contains_source_health_status() -> None:
    from app.sources import SourceRunState

    ted = FakeSource(
        "ted",
        [notice("ted", "1"), notice("ted", "2")],
    )
    sam = FakeSource(
        "sam",
        error=RuntimeError("upstream unavailable"),
    )

    registry = SourceRegistry(
        [
            SourceRegistration("ted", "TED", ted),
            SourceRegistration("sam", "SAM.gov", sam),
        ]
    )

    report = asyncio.run(MultiSourceFetcher(registry).fetch())

    assert len(report.statuses) == 2

    ted_status = report.statuses[0]
    assert ted_status.source == "ted"
    assert ted_status.state == SourceRunState.OK
    assert ted_status.notice_count == 2
    assert ted_status.duration_ms >= 0
    assert ted_status.error_type is None

    sam_status = report.statuses[1]
    assert sam_status.source == "sam"
    assert sam_status.state == SourceRunState.FAILED
    assert sam_status.notice_count == 0
    assert sam_status.duration_ms >= 0
    assert sam_status.error_type == "RuntimeError"
    assert report.healthy is False


def test_explicit_disabled_source_is_not_fetched() -> None:
    disabled = FakeSource(
        "sam",
        [notice("sam", "A")],
    )

    registry = SourceRegistry(
        [
            SourceRegistration(
                "sam",
                "SAM.gov",
                disabled,
                enabled=False,
            )
        ]
    )

    report = asyncio.run(
        MultiSourceFetcher(registry).fetch(
            source_keys=["sam"],
        )
    )

    assert report.attempted_sources == ()
    assert report.statuses == ()
    assert disabled.calls == 0
