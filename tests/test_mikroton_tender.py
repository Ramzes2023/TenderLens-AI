"""Offline contract/security tests for the opt-in real MikroTon API connector."""
import asyncio
import json
from dataclasses import replace

import pytest

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.mikroton_tender import (
    SOURCE_ID, MikrotonTenderSource, parse_listing,
)


def item(identity=1):
    return {
        "id": identity, "title": "Поставка промышленного алюминия",
        "description": "Закупка металлопроката",
        "portal_url": f"https://tender.mt52.ru/tenders/{identity}",
        "created_at": "2026-06-01T12:00:00+03:00",
        "submission_deadline": "2026-10-19T14:00:00+03:00",
        "start_price": 12000.50, "currency": "RUB",
        "customer": {"id": 5, "name": 'ООО "МИКРОТОН"', "inn": "5263135670"},
    }


def envelope(rows):
    return json.dumps({"meta": {"api_version": "v1", "schema_version": "1.1"},
                       "items": rows}).encode("utf-8")


def test_normalizes_official_api_item_no_fabricated_fields():
    tender = parse_listing(envelope([item()]))[0]
    assert tender.source == SOURCE_ID
    assert tender.external_id == "1"
    assert tender.title == "Поставка промышленного алюминия"
    assert tender.initial_price == 12000.50
    assert tender.currency == "RUB"
    assert tender.customer == 'ООО "МИКРОТОН"'
    assert tender.published_at.endswith("+03:00")
    assert tender.deadline.endswith("+03:00")
    assert tender.url == "https://tender.mt52.ru/tenders/1"
    assert tender.region is None
    assert parse_listing(envelope([])) == []


@pytest.mark.parametrize("field,value", [
    ("id", True),
    ("id", "1"),
    ("title", "<script>x</script>"),
    ("portal_url", "https://evil.invalid/tenders/1"),
    ("portal_url", "https://tender.mt52.ru/tenders/2"),
    ("portal_url", "https://tender.mt52.ru/tenders/1#foo"),
    ("start_price", float("inf")),
    ("start_price", -1),
    ("created_at", "2026-06-01T12:00:00"),
    ("customer", "not-a-dict"),
])
def test_invalid_or_ambiguous_source_values_are_rejected(field, value):
    record = item()
    record[field] = value
    with pytest.raises((ValueError, TypeError)):
        parse_listing(envelope([record]))


def test_duplicate_identity_is_rejected():
    with pytest.raises(ValueError):
        parse_listing(envelope([item(), item()]))


def test_archive_unknown_price_is_preserved_as_unknown():
    record = item()
    record["start_price"] = None
    record["currency"] = "RUB"
    notice = parse_listing(envelope([record]))[0]
    assert notice.initial_price is None
    assert notice.currency is None


def test_default_disabled_and_explicit_opt_in_only():
    settings = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=10,
        max_notifications_per_cycle=5, request_timeout=15,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
    )
    catalog = build_source_catalog(settings)
    assert SOURCE_ID not in catalog.enabled_keys
    opted = build_source_catalog(replace(settings, mikroton_tender_enabled=True))
    assert SOURCE_ID in opted.enabled_keys
    assert opted.registry.get(SOURCE_ID).source.name == SOURCE_ID
    assert opted.registry.get(SOURCE_ID).metadata.official is False


def test_invalid_source_config_rejected():
    with pytest.raises(ValueError):
        MikrotonTenderSource(timeout=0)
    with pytest.raises(ValueError):
        MikrotonTenderSource(timeout=35)
    with pytest.raises(ValueError):
        MikrotonTenderSource(name="eis")
    with pytest.raises(ValueError):
        asyncio.run(MikrotonTenderSource().fetch(limit=0))


def test_public_description_html_becomes_safe_plain_text():
    record = item()
    record["description"] = (
        '<p>Поставка листового алюминия</p><script>steal_secret()</script>'
        '<div>Для предприятия &amp; цеха</div>'
    )
    result = parse_listing(envelope([record]))[0]
    assert result.summary == "Поставка листового алюминия Для предприятия & цеха"
    assert "steal_secret" not in result.summary
    assert "<" not in result.summary


def test_public_html_title_is_not_accepted_as_procurement_name():
    record = item()
    record["title"] = "<b>Закупка</b>"
    with pytest.raises(ValueError):
        parse_listing(envelope([record]))
