"""Bounded, failure-isolated fetching across multiple procurement sources."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable

from .models import TenderNotice
from .registry import SourceRegistration, SourceRegistry


@dataclass(frozen=True, slots=True)
class SourceFailure:
    source: str
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class MultiSourceFetchReport:
    notices: tuple[TenderNotice, ...]
    failures: tuple[SourceFailure, ...]
    attempted_sources: tuple[str, ...]
    successful_sources: tuple[str, ...]

    @property
    def partial_failure(self) -> bool:
        return bool(self.failures) and bool(self.successful_sources)

    @property
    def total_failure(self) -> bool:
        return bool(self.failures) and not self.successful_sources


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
            selected.append(self.registry.get(key))
        return tuple(selected)

    async def fetch(
        self,
        *,
        limit_per_source: int = 20,
        source_keys: Iterable[str] | None = None,
    ) -> MultiSourceFetchReport:
        limit = max(1, min(int(limit_per_source), 100))
        selected = self._select(source_keys)
        semaphore = asyncio.Semaphore(self.concurrency)

        async def run_one(
            registration: SourceRegistration,
        ) -> tuple[
            str,
            list[TenderNotice] | None,
            SourceFailure | None,
        ]:
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

                return registration.key, notices, None
            except Exception as error:
                message = str(error).strip() or "Source fetch failed."
                return (
                    registration.key,
                    None,
                    SourceFailure(
                        source=registration.key,
                        error_type=type(error).__name__,
                        message=message[:500],
                    ),
                )

        results = await asyncio.gather(
            *(run_one(item) for item in selected)
        )

        merged: list[TenderNotice] = []
        failures: list[SourceFailure] = []
        successful: list[str] = []
        seen_notice_ids: set[tuple[str, str]] = set()

        for source_key, notices, failure in results:
            if failure is not None:
                failures.append(failure)
                continue

            successful.append(source_key)

            for notice in notices or ():
                if notice.identity in seen_notice_ids:
                    continue
                seen_notice_ids.add(notice.identity)
                merged.append(notice)

        return MultiSourceFetchReport(
            notices=tuple(merged),
            failures=tuple(failures),
            attempted_sources=tuple(item.key for item in selected),
            successful_sources=tuple(successful),
        )


__all__ = [
    "MultiSourceFetcher",
    "MultiSourceFetchReport",
    "SourceFailure",
]
