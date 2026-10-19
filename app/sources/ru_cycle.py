"""Explicit operator-only one-shot enqueue for independently live-tested Russian adapters.

No network, periodic scheduling, production activation, source discovery, credentials,
or employee/company data. The existing durable job lease/fencing and hourly
idempotency remain authoritative when an operator separately runs this CLI.
"""
from __future__ import annotations

from .registry import SourceRegistryError

# Only adapters with a first-party/live buyer list→notice→leased Worker→SQL
# acceptance previously checked; platform research/blocked PRs are excluded.
# This is a *publisher-connection* allowlist, not independent procurement
# publication counts: buyer and marketplace copies can overlap.
RU_APPROVED_SOURCES = (
    "b2b_center",
    "lenobl_small_public",
    "nmck_native_public",
    "mikroton_tender",
    "south_ural_public",
    "stan_commercial_public",
    "kavkaz_rf_firstparty",
)


def approved_ru_keys(catalog):
    """Return exactly operator-enabled, registered RU sources in fixed order."""
    approved = []
    for key in RU_APPROVED_SOURCES:
        try:
            item = catalog.registry.get(key)
        except SourceRegistryError:
            continue  # Operator did not activate this adapter in config.
        if "RU" not in item.jurisdictions:
            raise ValueError("Approved Russian source has non-RU jurisdiction.")
        if item.enabled:
            approved.append(key)
    if not approved:
        raise ValueError("No operator-approved Russian sources are enabled.")
    return tuple(approved)


def enqueue_approved_ru(service, catalog, *, now=None):
    """Put only explicitly enabled source jobs in the existing durable queue.

    Per-source idempotency is enforced by ConnectorSyncService (UTC hour,
    adapter version and source). This function does not start workers.
    """
    result = {}
    for key in approved_ru_keys(catalog):
        job = service.enqueue(key, now=now)
        result[key] = {"job_id": job.id, "state": job.state}
    return result
