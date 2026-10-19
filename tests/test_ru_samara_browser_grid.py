"""Offline hostile/structural tests ONLY; never evidence of live Samara tenders."""
import json

import pytest

from scripts.research_ru_samara_browser_grid import (
    GRID, HOST, JSON_PATH, allowed, public_post_names,
    public_row_shape, safe_original_reference,
)


def test_first_party_methods_and_login_pages_are_restricted():
    assert allowed(GRID, "GET")
    assert allowed(f"https://{HOST}{JSON_PATH}", "POST")
    assert not allowed(f"https://{HOST}{JSON_PATH}", "GET")
    assert not allowed(f"https://{HOST}{JSON_PATH}", "PUT")
    assert not allowed(f"https://{HOST}/smallpurchases/Login/Form", "GET")
    assert not allowed(f"https://{HOST}.evil.invalid{JSON_PATH}", "POST")
    assert not allowed(f"http://{HOST}{JSON_PATH}", "POST")
    assert not allowed(f"https://x@{HOST}{JSON_PATH}", "POST")
    assert not allowed(f"https://{HOST}:444{JSON_PATH}", "POST")


def test_original_reference_is_pinned_and_not_guessed():
    assert safe_original_reference("/smallpurchases/GzwSP/5611196")
    for u in (None, "", "//evil.invalid/n", "https://evil.invalid/detail",
              "/login", "/smallpurchases/Login/Form",
              "/smallpurchases/GzwSP/123?token=secret",
              "/smallpurchases/GzwSP/123#fragment", "/smallpurchases/\\evil"):
        assert not safe_original_reference(u)


def test_public_post_logs_names_only_and_never_contents():
    payload = '{"settings":{"token":"VERY_SECRET"},"csrf":"ALSO_SECRET"}'
    assert public_post_names(payload, "application/json") == ("csrf", "settings")
    assert public_post_names("settings=%7B%7D&token=secret", "application/x-www-form-urlencoded") == (
        "settings", "token",
    )
    assert public_post_names("{oops", "application/json") == ()


def _row(number):
    return {
        "number": number,
        "name": "Example equipment purchase",
        "uchr_sname": "Example municipal institution",
        "link": "/smallpurchases/GzwSP/5611196",
    }


def test_synthetic_offline_native_list_is_bounded_and_not_detail_proof():
    obj = {"items": [
        _row("ИМЗ-2026-123456"),
        _row("ИМЗ-2026-123457"),
    ]}
    result = public_row_shape(json.dumps(obj, ensure_ascii=False).encode())
    assert result == {"rows": 2, "native_ids": 2, "same_host_detail_refs": 2}
    obj["items"][1]["link"] = "https://evil.invalid/phishing"
    assert public_row_shape(json.dumps(obj, ensure_ascii=False).encode())["same_host_detail_refs"] == 1


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(items=[]),
    lambda d: d.update(items=[_row("ИМЗ-2026-123456")]),
    lambda d: d["items"][1].update(number="ИМЗ-2026-123456"),
    lambda d: d["items"][1].update(number="EIS-123"),
    lambda d: d["items"][0].update(uchr_sname=""),
    lambda d: d["items"][0].update(name="a"),
    lambda d: d.update(items=[_row(f"ИМЗ-2026-{n:06d}") for n in range(31)]),
])
def test_fake_incomplete_duplicate_and_unbounded_rows_fail_closed(mutate):
    d = {"items": [_row("ИМЗ-2026-123456"), _row("ИМЗ-2026-123457")]}
    mutate(d)
    with pytest.raises(ValueError):
        public_row_shape(json.dumps(d, ensure_ascii=False).encode())
