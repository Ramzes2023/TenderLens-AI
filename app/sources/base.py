"""Common contract for procurement source adapters."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import TenderNotice


@runtime_checkable
class TenderSource(Protocol):
    """Minimal contract implemented by every procurement source adapter."""

    @property
    def name(self) -> str:
        ...

    async def fetch(self, limit: int = 20) -> list[TenderNotice]:
        ...


__all__ = ["TenderSource"]
