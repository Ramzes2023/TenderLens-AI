"""Offline Lenobl V6 same-network read-only canary, no real HTTP."""
import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from app.sources.http import BoundedClient
from app.sources.lenobl_small_public import HOST, LIST_URL
from app.sources.lenobl_v6_canary import (
    _failure_label, main, probe_source, safe_environment,
)


def allowed_env():
    return {
        "DATABASE_URL": "sqlite:////app/data/isolated-public-sources.sqlite3",
        "VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED": "true",
        "MONITORING_ENABLED": "false",
        "TELEGRAM_BOT_TOKEN": "",
        "VALYQON_EMAIL_MODE": "disabled",
        "VALYQON_RESTRICT_PAID_SOURCE_DETAILS": "true",
        "LENOBL_SMALL_PUBLIC_ENABLED": "true",
        "VALYQON_CONNECTOR_MAX_RECORDS": "30",
        "OUTBOUND_PROXY_URL": "",
        "VALYQON_RU_BACKGROUND_CATALOG_ENABLED": "false",
    }


def _official_listing():
    title = "Поставка компьютерной техники и расходных материалов"
    return ("<html><body>" + "".join(
        f"<a href='/ProductRequestGroup/Index/{35217482+i}'>{title}</a>"
        for i in range(6)
    ) + "</body></html>").encode("utf-8")


def _official_detail(identity):
    return (
        "<html><body><h1>Закупка: поставка компьютерной техники "
        "и расходных материалов</h1>"
        f"<p>Группа закупок № {identity}</p>"
        "<p>Срок окончания подачи оферт: 15 ноября 2026 г. 12:30:00</p>"
        "</body></html>"
    ).encode("utf-8")


def _mock_http(monkeypatch, handler):
    original = BoundedClient.__init__

    def init(instance, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(instance, **kwargs)

    monkeypatch.setattr(BoundedClient, "__init__", init)


def test_safe_env_rejects_unsafe_runtime_before_network(monkeypatch):
    assert safe_environment(allowed_env())
    for change in (
        {"DATABASE_URL": "sqlite:///./production.db"},
        {"MONITORING_ENABLED": "true"},
        {"TELEGRAM_BOT_TOKEN": "private-secret"},
        {"LENOBL_SMALL_PUBLIC_ENABLED": "false"},
        {"VALYQON_CONNECTOR_MAX_RECORDS": "20"},
        {"OUTBOUND_PROXY_URL": "http://proxy.invalid"},
        {"VALYQON_RU_BACKGROUND_CATALOG_ENABLED": "true"},
    ):
        assert not safe_environment({**allowed_env(), **change})
    assert main({**allowed_env(), "MONITORING_ENABLED": "true"}) == 2


def test_exact_v6_budget_real_parser_under_offline_transport(monkeypatch):
    calls = []

    def handler(request):
        url = str(request.url)
        calls.append(url)
        if url == LIST_URL:
            body = _official_listing()
        else:
            assert url.startswith(f"https://{HOST}/ProductRequestGroup/Index/")
            body = _official_detail(url.rsplit("/", 1)[-1])
        return httpx.Response(
            200, content=body, headers={"content-type": "text/html"},
        )

    _mock_http(monkeypatch, handler)
    now = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
    data = asyncio.run(probe_source(now=now))
    assert data["status"] == "SOURCE_GET_CANDIDATE_ONLY"
    assert data["verified_originals"] == 3
    assert data["safely_open_originals"] == 3
    assert data["observed_http_gets"] == 4
    assert len(calls) == 4
    assert data["worker_sql_receipt_proved"] is False
    assert data["public_https_delivery_proved"] is False
    assert data["telegram_send_authorized"] is False
    assert data["production_changed"] is False


def test_failed_publisher_never_leaks_exception_text(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("SENSITIVE_PRIVATE_SOURCE_DETAIL")

    _mock_http(monkeypatch, handler)
    data = asyncio.run(probe_source(
        now=datetime(2026, 10, 29, 12, tzinfo=timezone.utc),
    ))
    assert data["status"] == "BLOCKED_FIRSTPARTY_SOURCE"
    assert data["verified_originals"] == 0
    assert "SENSITIVE" not in str(data)
    assert data["exception_class"] != "none"
    assert data["production_changed"] is False


@pytest.mark.parametrize("error,expected", [
    (ValueError("private credentials"), ("ValueError", "none")),
    (RuntimeError("private data"), ("RuntimeError", "none")),
])
def test_exception_classification_only(error, expected):
    assert _failure_label(error) == expected
