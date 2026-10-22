"""Catalog-compatible read adapter. No HTTP fallback or automatic refresh."""
import asyncio
from datetime import datetime, timedelta, timezone
from dataclasses import replace

from .catalog import SourceCatalog
from .multi import MultiSourceFetcher
from .registry import SourceRegistry


class SnapshotSource:
    local_keyword_search = True  # Local snapshots filter terms even if live profile feeds are disabled.

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


# Strictly opt-in Worker-SQL route for only these independently verified
# official / accredited Ingushetia originals. All unrelated live sources
# remain unchanged, including tenant-specific EIS searches.
_INGUSHETIA_WORKER_KEYS = frozenset({
    "ru_ingushetia_eis44", "ru_ingushetia_fabrikant44",
})
# ConnectorSyncService uses one idempotent job per UTC hour. A 30-minute
# snapshot TTL wrongly makes the bot declare a healthy hourly run stale for
# half the hour. Allow one full hour plus 15 minutes of bounded scheduling
# drift; still fail closed if the source is not refreshed within that window.
INGUSHETIA_WORKER_MAX_AGE_SECONDS = 75 * 60


class FreshIngushetiaWorkerSource(SnapshotSource):
    """Never fall back to the network or notify from stale Worker storage."""

    def __init__(self, repository, name, terms=()):
        if name not in _INGUSHETIA_WORKER_KEYS:
            raise ValueError("Unapproved regional snapshot source")
        super().__init__(repository, name, terms)

    def for_search_terms(self, terms, *, max_feeds=5):
        return FreshIngushetiaWorkerSource(self.repository, self.name, tuple(terms)[:20])

    async def fetch(self, limit=20):
        seen = await asyncio.to_thread(self.repository.latest_seen_utc, self.name)
        now = datetime.now(timezone.utc)
        lower = now - timedelta(seconds=INGUSHETIA_WORKER_MAX_AGE_SECONDS)
        # A source is healthy only after a successful, recent actual Worker
        # persistence. Future-dated SQL records fail closed on clock skew.
        if seen is None or not lower <= seen <= now + timedelta(seconds=120):
            raise ValueError("Ingushetia Worker SQL source is absent or stale")
        # Include ONLY notices observed within the freshness window; a fresh
        # single record cannot resurrect an old unnotified procurement.
        # Stored DB exact-substring searches are not a substitute for the
        # monitor's Russian morphology matching: "оборудование" should
        # match a profile keyword "оборудования" without querying upstream.
        # Filter terms locally using the same tokenizer *before* applying
        # the notification limit, to avoid undercounting legitimate matches.
        records = await asyncio.to_thread(
            self.repository.read, self.name, 100, (), not_before=lower,
        )
        if not self.terms:
            return records[:limit]
        from app.monitoring.service import _term_match
        def match(notice):
            text = " ".join(str(v or "") for v in (
                notice.title, notice.summary, notice.tender_number,
                notice.external_id, notice.customer, notice.region, notice.url,
            ))
            # Use exactly the monitor's token/inflection contract. A raw
            # substring ("газ" inside "Газпром", "металл" inside unrelated
            # longer words) would consume the 100-row candidate limit
            # before legitimate subscriber matches are considered.
            return any(_term_match(text, term) for term in self.terms)
        return [notice for notice in records if match(notice)][:limit]


def fresh_ingushetia_worker_catalog(catalog, repository):
    """Wrap only operator-enabled regional sources with verified fresh SQL.

    This does not enqueue or run a Worker, schedule polls, or send Telegram.
    All other enabled national / commercial adapters retain normal semantics.
    """
    active = _INGUSHETIA_WORKER_KEYS.intersection(catalog.enabled_keys)
    if not active:
        raise ValueError("No operator-enabled Ingushetia sources for Worker SQL")
    registry = SourceRegistry(
        replace(item, source=FreshIngushetiaWorkerSource(repository, item.key))
        if item.key in active else item
        for item in catalog.registry.registrations()
    )
    return SourceCatalog(registry, MultiSourceFetcher(registry, concurrency=1))
