"""One-shot operator-only cycle for approved, individually enabled CIS sources.

No scheduler, auto-discovery, production activation, customer profile, or HTTP
fetch. Existing queue idempotency bounds duplicate requests to one UTC hour.
"""
from __future__ import annotations

APPROVED_CIS_SOURCES = ("md_elicitatie", "az_azeristilik", "az_adif_small")


def approved_cis_keys(catalog):
    """Fail closed if the operator has not explicitly enabled a reviewed source."""
    keys = tuple(
        name for name in APPROVED_CIS_SOURCES
        if catalog.registry.get(name).enabled
    )
    if not keys:
        raise ValueError("No operator-approved CIS sources are enabled.")
    return keys


def enqueue_approved_cis(service, catalog, *, now=None):
    """Queue approved sources only; no live fetch and no automatic enablement."""
    keys = approved_cis_keys(catalog)
    result = {}
    for name in keys:
        job = service.enqueue(name, now=now)
        result[name] = {"job_id": job.id, "state": job.state}
    return result
