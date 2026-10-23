"""Bounded, failure-isolated fetching across procurement sources."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from time import perf_counter
from typing import Iterable

from .models import TenderNotice
from .ru_dedup import deduplicate
from .registry import SourceRegistration, SourceRegistry


@dataclass(frozen=True, slots=True)
class SourceFailure:
    source: str
    error_type: str
    message: str


class SourceRunState(StrEnum):
    OK = "ok"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SourceRunStatus:
    source: str
    state: SourceRunState
    notice_count: int
    duration_ms: int
    error_type: str | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class MultiSourceFetchReport:
    notices: tuple[TenderNotice, ...]
    failures: tuple[SourceFailure, ...]
    attempted_sources: tuple[str, ...]
    successful_sources: tuple[str, ...]
    statuses: tuple[SourceRunStatus, ...]
    duplicate_provenance: tuple[tuple[TenderNotice, ...], ...] = ()

    @property
    def partial_failure(self) -> bool:
        return bool(self.failures) and bool(self.successful_sources)

    @property
    def total_failure(self) -> bool:
        return bool(self.failures) and not self.successful_sources

    @property
    def healthy(self) -> bool:
        return not self.failures


class MultiSourceFetcher:
    """Fetch registered sources concurrently without one failure stopping others."""

    def __init__(
        self,
        registry: SourceRegistry,
        *,
        concurrency: int = 8,
    ) -> None:
        self.registry = registry
        self.concurrency = max(1, min(int(concurrency), 32))

    def _select(
        self,
        source_keys: Iterable[str] | None,
    ) -> tuple[SourceRegistration, ...]:
        if source_keys is None:
            return self.registry.registrations(enabled_only=True)

        selected: list[SourceRegistration] = []
        seen: set[str] = set()

        for raw_key in source_keys:
            key = str(raw_key).strip()
            if key in seen:
                continue

            seen.add(key)
            registration = self.registry.get(key)

            if registration.enabled:
                selected.append(registration)

        return tuple(selected)

    async def fetch(
        self,
        *,
        limit_per_source: int = 20,
        source_keys: Iterable[str] | None = None,
    ) -> MultiSourceFetchReport:
        selected = self._select(source_keys)
        # Extended scans must NEVER expand an upstream HTTP/API request.
        # They are reserved for the opt-in, already persisted and time-
        # bounded Ingushetia Worker SQL sources. This lets a subscriber
        # reach a 101st match after the first 100 originals are seen.
        from .snapshots import FreshIngushetiaWorkerSource
        sql_only = bool(selected) and all(
            isinstance(item.source, FreshIngushetiaWorkerSource)
            and item.key in {"ru_ingushetia_eis44", "ru_ingushetia_fabrikant44"}
            for item in selected
        )
        maximum = 1000 if sql_only else 100
        limit = max(1, min(int(limit_per_source), maximum))
        semaphore = asyncio.Semaphore(self.concurrency)

        async def run_one(
            registration: SourceRegistration,
        ) -> tuple[
            str,
            list[TenderNotice] | None,
            SourceFailure | None,
            SourceRunStatus,
        ]:
            started = perf_counter()

            try:
                async with semaphore:
                    notices = await registration.source.fetch(limit)

                for notice in notices:
                    if notice.source != registration.key:
                        raise ValueError(
                            "Adapter returned notice with mismatched source key."
                        )

                    if not notice.external_id.strip():
                        raise ValueError(
                            "Adapter returned notice without external_id."
                        )

                    if not notice.url.strip():
                        raise ValueError(
                            "Adapter returned notice without URL."
                        )

                duration_ms = max(
                    0,
                    int((perf_counter() - started) * 1000),
                )

                return (
                    registration.key,
                    notices,
                    None,
                    SourceRunStatus(
                        source=registration.key,
                        state=SourceRunState.OK,
                        notice_count=len(notices),
                        duration_ms=duration_ms,
                    ),
                )

            except Exception as error:
                duration_ms = max(
                    0,
                    int((perf_counter() - started) * 1000),
                )

                # Regional live connectors can fail with third-party URLs
                # or proxy credentials embedded inside nested exceptions.
                # SourceRunStatus/SourceFailure are returned to consumer code,
                # so do not expose the vendor exception text in those public
                # records. Diagnostics live in separately redacted CI output.
                if registration.key in {
                    "ru_ingushetia_eis44", "ru_ingushetia_fabrikant44",
                }:
                    message = "Regional source unavailable; inspect restricted diagnostics."
                else:
                    message = str(error).strip() or "Source fetch failed."

                failure = SourceFailure(
                    source=registration.key,
                    error_type=type(error).__name__,
                    message=message[:500],
                )

                return (
                    registration.key,
                    None,
                    failure,
                    SourceRunStatus(
                        source=registration.key,
                        state=SourceRunState.FAILED,
                        notice_count=0,
                        duration_ms=duration_ms,
                        error_type=failure.error_type,
                        message=failure.message,
                    ),
                )

        results = await asyncio.gather(
            *(run_one(item) for item in selected)
        )

        # VALYQON BALANCED SOURCE MERGE V1
        #
        # Keep every successful source represented instead of allowing
        # the first source in registry order to fill a downstream cap.
        merged: list[TenderNotice] = []
        failures: list[SourceFailure] = []
        successful: list[str] = []
        statuses: list[SourceRunStatus] = []
        seen_notice_ids: set[tuple[str, str]] = set()
        source_notice_lists: list[list[TenderNotice]] = []

        for source_key, notices, failure, status in results:
            statuses.append(status)

            if failure is not None:
                failures.append(failure)
                continue

            successful.append(source_key)
            unique_notices: list[TenderNotice] = []

            for notice in notices or ():
                if notice.identity in seen_notice_ids:
                    continue

                seen_notice_ids.add(notice.identity)
                unique_notices.append(notice)

            source_notice_lists.append(unique_notices)

        max_source_results = max(
            (
                len(source_notices)
                for source_notices
                in source_notice_lists
            ),
            default=0,
        )

        for index in range(max_source_results):
            for source_notices in source_notice_lists:
                if index < len(source_notices):
                    merged.append(
                        source_notices[index]
                    )

        # Merge only provably identical RU procedures; retain raw source identities.
        deduplicated, provenance = deduplicate(merged)
        return MultiSourceFetchReport(
            notices=deduplicated,
            duplicate_provenance=provenance,
            failures=tuple(failures),
            attempted_sources=tuple(item.key for item in selected),
            successful_sources=tuple(successful),
            statuses=tuple(statuses),
        )


__all__ = [
    "MultiSourceFetcher",
    "MultiSourceFetchReport",
    "SourceFailure",
    "SourceRunState",
    "SourceRunStatus",
]
