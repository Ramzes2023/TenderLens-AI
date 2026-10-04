"""Registry and metadata for procurement source adapters."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable
from urllib.parse import urlsplit

from .base import TenderSource


_SOURCE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(?:-[A-Z]{2})?$")


class SourceRegistryError(ValueError):
    pass


class SourceTransport(StrEnum):
    API = "api"
    RSS = "rss"
    ATOM = "atom"
    HTML = "html"
    DATASET = "dataset"


@dataclass(frozen=True, slots=True)
class SourceCapabilities:
    keyword_search: bool = False
    pagination: bool = False
    documents: bool = False
    incremental_sync: bool = False
    authentication_required: bool = False


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    key: str
    display_name: str
    transport: SourceTransport
    jurisdictions: tuple[str, ...]
    languages: tuple[str, ...]
    homepage_url: str | None
    official: bool
    enabled: bool
    capabilities: SourceCapabilities


@dataclass(frozen=True, slots=True)
class SourceRegistration:
    """One configured procurement source and its public metadata."""

    key: str
    display_name: str
    source: TenderSource
    transport: SourceTransport = SourceTransport.API
    jurisdictions: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    homepage_url: str | None = None
    official: bool = True
    enabled: bool = True
    capabilities: SourceCapabilities = SourceCapabilities()

    def __post_init__(self) -> None:
        if not _SOURCE_KEY_RE.fullmatch(self.key):
            raise SourceRegistryError(
                "Source key must use lowercase letters, digits, '_' or '-'."
            )

        if not self.display_name.strip():
            raise SourceRegistryError(
                "Source display_name must not be empty."
            )

        if getattr(self.source, "name", None) != self.key:
            raise SourceRegistryError(
                f"Adapter name {getattr(self.source, 'name', None)!r} "
                f"does not match registry key {self.key!r}."
            )

        if self.homepage_url is not None:
            parsed = urlsplit(self.homepage_url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise SourceRegistryError(
                    "Source homepage_url must be a public HTTPS URL."
                )

        for jurisdiction in self.jurisdictions:
            if not jurisdiction.strip():
                raise SourceRegistryError(
                    "Source jurisdictions must not contain empty values."
                )

        for language in self.languages:
            if not _LANGUAGE_RE.fullmatch(language):
                raise SourceRegistryError(
                    f"Invalid source language code {language!r}."
                )

    @property
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            key=self.key,
            display_name=self.display_name,
            transport=self.transport,
            jurisdictions=self.jurisdictions,
            languages=self.languages,
            homepage_url=self.homepage_url,
            official=self.official,
            enabled=self.enabled,
            capabilities=self.capabilities,
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

    def metadata(
        self,
        *,
        enabled_only: bool = False,
    ) -> tuple[SourceMetadata, ...]:
        return tuple(
            item.metadata
            for item in self.registrations(enabled_only=enabled_only)
        )

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
    "SourceCapabilities",
    "SourceMetadata",
    "SourceRegistration",
    "SourceRegistry",
    "SourceRegistryError",
    "SourceTransport",
]
