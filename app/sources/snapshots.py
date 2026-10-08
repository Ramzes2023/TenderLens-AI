"""Catalog-compatible read adapter. No HTTP fallback or automatic refresh."""
import asyncio
from dataclasses import replace

from .catalog import SourceCatalog
from .multi import MultiSourceFetcher
from .registry import SourceRegistry


class SnapshotSource:
    def __init__(self, repository, name, terms=()):
        self.repository, self.name, self.terms = repository, name, terms

    def for_search_terms(self, terms, *, max_feeds=5):
        return SnapshotSource(self.repository, self.name, tuple(terms)[:20])

    async def fetch(self, limit=20):
        return await asyncio.to_thread(self.repository.read, self.name, limit, self.terms)


def snapshot_catalog(catalog, repository):
    registry = SourceRegistry(replace(item, source=SnapshotSource(repository, item.key))
                              for item in catalog.registry.registrations())
    return SourceCatalog(registry, MultiSourceFetcher(registry, concurrency=1))
