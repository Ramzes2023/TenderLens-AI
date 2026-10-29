"""Lenobl V6 connector's exact 4-request policy: one list + <=3 details.

OFFLINE MOCK ONLY. Tests do not contact the live official publisher.
"""
import asyncio

import httpx
import pytest

from app.sources.http import BoundedClient, FetchPolicy, bounded_fetch
from app.sources.lenobl_small_public import HOST, LIST_URL, LenoblSmallPublicSource


def _listing(count=6):
    title = "Поставка компьютерной техники и расходных материалов"
    body = "".join(
        f"<a href='/ProductRequestGroup/Index/{35217482+i}'>{title}</a>"
        for i in range(count)
    )
    return f"<html><body>{body}</body></html>".encode("utf8")


def _detail(id_number):
    return (
        f"<html><body><h1>Закупка: поставка компьютерной техники "
        f"и расходных материалов</h1>"
        f"<p>Группа закупок № {id_number}</p></body></html>"
    ).encode("utf8")


def _transport(monkeypatch, calls):
    def handler(request):
        calls.append(str(request.url))
        if str(request.url) == LIST_URL:
            return httpx.Response(200, content=_listing(),
                                  headers={"content-type": "text/html; charset=utf-8"})
        return httpx.Response(
            200, content=_detail(str(request.url).split("/")[-1]),
            headers={"content-type": "text/html; charset=utf-8"},
        )

    original = BoundedClient.__init__
    def init(instance, **kwargs):
        return original(instance, **dict(
            kwargs, transport=httpx.MockTransport(handler)
        ))
    monkeypatch.setattr(BoundedClient, "__init__", init)


def test_v6_max_records_30_stays_within_four_requests(monkeypatch):
    calls = []
    _transport(monkeypatch, calls)
    with bounded_fetch(FetchPolicy(frozenset({HOST}), max_requests=4)):
        notices = asyncio.run(LenoblSmallPublicSource().fetch(30))
    assert len(notices) == 3
    assert len({n.external_id for n in notices}) == 3
    assert calls == [LIST_URL] + [
        f"https://{HOST}/ProductRequestGroup/Index/{35217482+i}"
        for i in range(3)
    ]


def test_prior_policy_consumption_reserves_listing_request(monkeypatch):
    calls = []
    _transport(monkeypatch, calls)
    policy = FetchPolicy(frozenset({HOST}), max_requests=4, requests=2)
    with bounded_fetch(policy):
        notices = asyncio.run(LenoblSmallPublicSource().fetch(30))
    assert len(notices) == 1
    assert policy.requests == 4
    assert len(calls) == 2


def test_no_detail_budget_denies_before_any_network(monkeypatch):
    calls = []
    _transport(monkeypatch, calls)
    with bounded_fetch(FetchPolicy(frozenset({HOST}), max_requests=1)):
        with pytest.raises(ValueError, match="listing and detail request slots"):
            asyncio.run(LenoblSmallPublicSource().fetch(30))
    assert calls == []


def test_unbounded_direct_fetch_keeps_old_six_details(monkeypatch):
    # Direct source acceptance (without a Worker request cap) retains its
    # existing independent verified-list limit. No arbitrary new calls.
    calls = []
    _transport(monkeypatch, calls)
    notices = asyncio.run(LenoblSmallPublicSource().fetch(30))
    assert len(notices) == 6
    assert len(calls) == 7
