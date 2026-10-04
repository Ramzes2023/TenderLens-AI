"""Registry for procurement source adapters and their metadata."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .base import TenderSource


_SOURCE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class SourceRegistryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SourceRegistration:
    """One configured procurement source."""

    key: str
    display_name: str
    source: TenderSource
    jurisdictions: tuple[str, ...] = ()
    homepage_url: str | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if not _SOURCE_KEY_RE.fullmatch(self.key):
            raise SourceRegistryError(
                "Source key must use lowercase letters, digits, '_' or '-'."
            )
        if not self.display_name.strip():
            raise SourceRegistryError("Source display_name must not be empty.")
        if getattr(self.source, "name", None) != self.key:
            raise SourceRegistryError(
                f"Adapter name {getattr(self.source, 'name', None)!r} "
                f"does not match registry key {self.key!r}."
            )


class SourceRegistry:
    """Deterministic in-memory registry for source adapters."""

    def __init__(
        self,
        registrations: Iterable[SourceRegistration] = (),
    ) -> None:
        self._items: dict[str, SourceRegistration] = {}
        for registration in registrations:
            self.register(registration)

    def register(self, registration: SourceRegistration) -> None:
        if registration.key in self._items:
            raise SourceRegistryError(
                f"Source {registration.key!r} is already registered."
            )
        self._items[registration.key] = registration

    def get(self, key: str) -> SourceRegistration:
        try:
            return self._items[key]
        except KeyError:
            raise SourceRegistryError(
                f"Unknown source {key!r}."
            ) from None

    def registrations(
        self,
        *,
        enabled_only: bool = False,
    ) -> tuple[SourceRegistration, ...]:
        values = tuple(self._items.values())
        if not enabled_only:
            return values
        return tuple(item for item in values if item.enabled)

    def keys(
        self,
        *,
        enabled_only: bool = False,
    ) -> tuple[str, ...]:
        return tuple(
            item.key
            for item in self.registrations(enabled_only=enabled_only)
        )

    def __len__(self) -> int:
        return len(self._items)


__all__ = [
    "SourceRegistration",
    "SourceRegistry",
    "SourceRegistryError",
]
