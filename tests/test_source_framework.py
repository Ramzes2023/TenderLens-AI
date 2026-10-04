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
