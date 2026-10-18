"""Browser research helpers: reject untrusted origins and payload values."""
import pytest

from scripts.research_ru_dagestan_browser_grid import (
    HOST, LISTING, NATIVE, allowed, only_public_keynames,
    public_native_settings_shape, public_original_link_shape,
)


def test_fixed_public_browser_routes_are_read_only():
    assert allowed(LISTING, "GET")
    assert allowed(f"https://{HOST}{NATIVE}", "POST")
    assert allowed(f"https://{HOST}/Scripts/jquery.min.js", "GET")
    assert not allowed(f"https://{HOST}{NATIVE}", "GET")
    assert not allowed(f"https://{HOST}/logout", "GET")
    assert not allowed(f"https://{HOST}/login", "GET")
    assert not allowed(f"https://{HOST}/smallpurchases/GzwSP/NoticesGrid", "POST")


@pytest.mark.parametrize("url", [
    "http://goszakaz.e-dag.ru/smallpurchases/GzwSP/NoticesGrid",
    "https://goszakaz.e-dag.ru.evil.test/smallpurchases/GzwSP/NoticesGrid",
    "https://user:pw@goszakaz.e-dag.ru/smallpurchases/GzwSP/NoticesGrid",
    "https://other.test/smallpurchases/GzwSP/NoticesGrid",
    "file:///etc/passwd",
])
def test_bad_origins_refused(url):
    assert not allowed(url, "GET")


def test_log_only_param_names_not_sensitive_data():
    raw = ("page=1&rows=5&__RequestVerificationToken="
           "SECRET_VALUE_NEVER_LOGGED&keyword=%D1%88%D0%BA%D0%BE%D0%BB%D0%B0")
    keys = only_public_keynames(raw, "application/x-www-form-urlencoded")
    assert keys == ("__RequestVerificationToken", "keyword", "page", "rows")
    assert "SECRET_VALUE_NEVER_LOGGED" not in ",".join(keys)


def test_json_shape_keynames_are_static():
    names = only_public_keynames(
        '{"page": 1, "limit": 5, "antiforgery": "SECRET_VALUE_NEVER_LOGGED"}',
        "application/json",
    )
    assert names == ("antiforgery", "limit", "page")


def test_only_public_native_settings_field_names_and_types_no_values():
    import json
    from urllib.parse import urlencode
    token = "DO_NOT_PRINT_ANONYMOUS_SESSION_TOKEN"
    payload = urlencode({"settings": json.dumps({
        "page": 1, "pageSize": 10, "csrf": token,
    })})
    keys, types = public_native_settings_shape(payload)
    assert keys == ("csrf", "page", "pageSize")
    assert types == ("csrf:str", "page:int", "pageSize:int")
    assert token not in repr((keys, types))
    assert public_native_settings_shape("settings=not%20json") == ((), ())
    assert public_native_settings_shape("settings=1") == ((), ())
    assert public_native_settings_shape("settings=%7B%7D&settings=%7B%7D") == ((), ())


def test_only_genuine_first_party_dagestan_link_paths_and_no_query_values():
    original = ("/smallpurchases/GzwSP/Notice/123"
                "?__RequestVerificationToken=SECRET_NEVER_DISPLAY")
    assert public_original_link_shape(original) == "/smallpurchases/GzwSP/Notice/123"
    assert public_original_link_shape("https://evil.example/smallpurchases/GzwSP/Notice/123") == "NON_FIRST_PARTY"
    assert public_original_link_shape("javascript:alert(1)") == "NON_FIRST_PARTY"
    assert public_original_link_shape(None) == "MISSING_OR_NONSTRING"
