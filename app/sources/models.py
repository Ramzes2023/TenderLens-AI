"""Normalized tender notice returned by external sources."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TenderNotice:
    source: str
    external_id: str
    title: str
    url: str
    published_at: str | None = None
    tender_number: str | None = None
    customer: str | None = None
    initial_price: float | None = None
    currency: str | None = None
    deadline: str | None = None
    region: str | None = None
    summary: str | None = None

    @property
    def identity(self) -> tuple[str, str]:
        return self.source, self.external_id
