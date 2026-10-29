"""Lenobl source request budget matches the exact first-party listing/detail cap.

Offline only: synthetic notices, no HTTP, databases, credentials or notification I/O.
"""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.jobs.models import JobScope
from app.sources import ingestion
from app.sources.lenobl_small_public import HOST, MAX_DETAILS, SOURCE_ID
from app.sources.models import TenderNotice


@pytest.mark.parametrize("max_records,expected", [(1, 2), (3, 4), (20, 7), (30, 7)])
def test_lenobl_worker_has_one_list_call_and_one_per_verified_detail(
    monkeypatch, max_records, expected,
):
    budgets = []
    fetched_limits = []
    written = []

    @contextmanager
    def fake_policy(policy):
        assert policy.hosts == frozenset({HOST})
        budgets.append(policy.max_requests)
        yield

    async def fake_fetch(limit):
        fetched_limits.append(limit)
        # The source caps verification at MAX_DETAILS; the public portal returns
        # the configured number of distinct first-party detail candidates.
        return [
            TenderNotice(
                source=SOURCE_ID,
                external_id=str(35217000 + number),
                title=f"Поставка компьютерного оборудования {number}",
                url=f"https://{HOST}/ProductRequestGroup/Index/{35217000 + number}",
            )
            for number in range(min(limit, MAX_DETAILS))
        ]

    source = SimpleNamespace(fetch=fake_fetch)
    registration = SimpleNamespace(key=SOURCE_ID, source=source, enabled=True)
    catalog = SimpleNamespace(
        registry=SimpleNamespace(get=lambda key: registration),
    )

    class MemoryOpportunities:
        def upsert_fenced(self, notice, version, fence):
            assert notice.source == SOURCE_ID
            written.append(notice.external_id)
            return True

    context = SimpleNamespace(
        job=SimpleNamespace(scope=JobScope()),
        should_stop=False,
        fenced_write=lambda write: True,
    )
    payload = {
        "schema": 1,
        "source_id": SOURCE_ID,
        "sync_window": "2026-10-29T12Z",
        "connector_version": ingestion.connector_version(SOURCE_ID),
    }
    monkeypatch.setattr(ingestion, "bounded_fetch", fake_policy)
    result = ingestion.ConnectorSyncHandler(
        catalog, MemoryOpportunities(), max_records=max_records,
    )(context, payload)

    assert budgets == [expected]
    assert fetched_limits == [max_records]
    assert result["accepted_count"] == min(max_records, MAX_DETAILS)
    assert len(written) == result["accepted_count"]


def test_exact_source_cap_is_six_details_not_unbounded():
    assert MAX_DETAILS == 6
