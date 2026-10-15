"""Offline regression for the live TED -> durable worker -> snapshot search gate.

These tests intentionally use synthetic notice data; they are never live proof.
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.sources.models import TenderNotice
from scripts.ci_ted_persisted_search import (
    AcceptanceFailure,
    accept,
    main,
)


class StubTed:
    name = "ted"

    def __init__(self, notices):
        self.notices = notices
        self.calls = 0

    async def fetch(self, limit=20):
        self.calls += 1
        return self.notices[:limit]


def sample(title="Electrical control cabinets and switchgear"):
    return TenderNotice(
        source="ted",
        external_id="099999-2026",
        title=title,
        url="https://ted.europa.eu/en/notice/-/detail/099999-2026",
        tender_number="099999-2026",
        published_at="2026-10-14",
    )


def test_disposable_worker_persists_and_searches_normalized_record(monkeypatch):
    # A production DATABASE_URL must never be used by this acceptance helper.
    monkeypatch.setenv("DATABASE_URL", "postgresql://do-not-touch.invalid/production")
    monkeypatch.setenv("VALYQON_DATABASE_REQUIRE_POSTGRES", "true")
    source = StubTed([sample()])
    result = accept(source)
    assert source.calls == 1
    assert result["source"] == "ted"
    assert result["normalized"] == 1
    assert result["persisted"] == 1
    assert result["searched"] == 1
    assert result["official_identity"] == "VERIFIED"
    assert result["snapshot_search"] == "VERIFIED"
    assert result["cross_source_isolation"] == "VERIFIED"
    assert result["idempotent_upsert"] == "VERIFIED"
    assert result["database"] == "ephemeral-sqlite"
    assert result["authenticated_browser_test"] is False


def test_empty_fetch_fails_closed_not_live_success():
    with pytest.raises(AcceptanceFailure, match="NO_ACCEPTED_NOTICES"):
        accept(StubTed([]))


@pytest.mark.parametrize(
    "mutant",
    [
        replace(sample(), url="https://example.net/en/notice/-/detail/099999-2026"),
        replace(sample(), tender_number="999998-2026"),
        replace(sample(), title="TED notice 099999-2026"),
    ],
)
def test_incorrect_identity_is_rejected(mutant):
    with pytest.raises(AcceptanceFailure, match="NON_AUTHORITATIVE_NOTICE"):
        accept(StubTed([mutant]))


def test_wrong_source_identity_does_not_pass_worker():
    with pytest.raises(Exception):
        accept(StubTed([replace(sample(), source="uk_fts")]))


def test_cli_requires_explicit_live_opt_in(capsys, monkeypatch):
    def forbidden_source(*args, **kwargs):
        raise AssertionError("no network adapter may be created")

    monkeypatch.setattr("scripts.ci_ted_persisted_search.TedApiSource", forbidden_source)
    assert main([]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "NOT_RUN"
    assert payload["outbound_calls"] == 0
    assert payload["reason"] == "LIVE_OPT_IN_REQUIRED"


def test_cli_sanitizes_network_exception(capsys, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE-UPSTREAM-CONTENT: TOKEN=SECRET")

    monkeypatch.setattr("scripts.ci_ted_persisted_search.accept", fail)
    assert main(["--live"]) == 1
    output = capsys.readouterr().out
    assert "PRIVATE-UPSTREAM-CONTENT" not in output
    assert "SECRET" not in output
    payload = json.loads(output)
    assert payload["status"] == "FAIL"
    assert payload["source"] == "ted"
    assert payload["stage"] == "RuntimeError"
