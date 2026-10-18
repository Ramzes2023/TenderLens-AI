"""Browser research helpers: reject untrusted origins and payload values."""
import pytest

from scripts.research_ru_dagestan_browser_grid import (
    HOST, LISTING, NATIVE, allowed, only_public_keynames,
    public_native_settings_shape, public_original_link_shape,
    public_native_settings_encoding, extract_public_native_settings,
    public_native_settings_public_defaults,
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


def test_real_browser_json_envelope_nested_settings_without_leaking_values():
    import json
    secret = "NO_SESSION_DATA_MAY_BE_PRINTED"
    payload = json.dumps({"settings": {
        "page": 1, "limit": 10, "csrf": secret, "sort": "pub_date",
    }})
    value = extract_public_native_settings(payload, "application/json")
    assert value["page"] == 1
    keys, types = public_native_settings_shape(payload, "application/json")
    assert keys == ("csrf", "limit", "page", "sort")
    assert types == ("csrf:str", "limit:int", "page:int", "sort:str")
    assert secret not in str(keys) + str(types)
    assert public_native_settings_encoding(payload, "application/json") == ("JSON_OBJECT", 4)
    assert extract_public_native_settings(payload, "text/html") is None
    assert extract_public_native_settings('{"settings":{},"password":"x"}', "application/json") is None
    assert public_native_settings_encoding('{"settings":null}', "application/json") == ("MISSING_OR_INVALID", 0)


def test_whitelisted_native_defaults_expose_only_public_pagination():
    import json
    payload = json.dumps({"settings": {
        "page": 1, "rp": 10, "totalRows": 999,
        "sortField": "pub_date", "sortDir": "desc",
        "sortList": {"pub_date": "Дата публикации", "name": "Наименование"},
        "filter": {"token": "HIDDEN_SECRET"},
        "rpList": [10, 25, 50],
        "localFilter": [],
    }})
    safe = public_native_settings_public_defaults(payload, "application/json")
    assert safe["page"] == 1
    assert safe["rp"] == 10
    assert safe["sortField"] == "pub_date"
    assert safe["rpList_public_numeric_values"] == (10, 25, 50)
    assert safe["filter_keys"] == ("token",)
    assert "HIDDEN_SECRET" not in str(safe)


def test_no_sensitive_public_default_echo_when_unrecognized_sort_or_filter():
    import json
    payload = json.dumps({"settings": {
        "sortField": "private_user_info",
        "sortDir": "stolenSECRET",
        "filter": {"Authorization": "SECRET_PASSWORD"},
        "rpList": [10, "SECRET_PASSWORD"],
    }})
    safe = public_native_settings_public_defaults(payload, "application/json")
    assert safe["sortField"] == "OTHER_COLUMN"
    assert safe["sortDir"] == "OTHER_DIRECTION"
    assert "SECRET_PASSWORD" not in str(safe)
    assert "stolenSECRET" not in str(safe)
