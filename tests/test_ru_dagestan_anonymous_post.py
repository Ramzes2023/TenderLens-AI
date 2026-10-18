"""Anonymous official Dagestan listing schema checks: synthetic, never live."""
import json
import pytest

from scripts.research_ru_dagestan_anonymous_post import (
    HOST, INDEX, PATH, URL, LIMIT, FORM, MAX_BYTES, published_route,
    parse_public_json,
)


def test_fixed_official_firstparty_path_and_post_form():
    assert HOST == "goszakaz.e-dag.ru"
    assert INDEX == "https://goszakaz.e-dag.ru/smallpurchases/GzwSP/NoticesGrid"
    assert PATH == "/smallpurchases/GzwSP/NoticesJson"
    assert URL == "https://" + HOST + PATH
    assert FORM == {"page": "1", "rows": str(LIMIT), "sidx": "", "sord": "desc"}


def test_requires_public_html_route_not_counters():
    assert published_route(b'<script src="/smallpurchases/GzwSP/NoticesJson"></script>')
    assert not published_route(b"<p>All tenders: 21,000</p>")
    assert not published_route(b"")
    assert not published_route(b"\x00" + PATH.encode("ascii"))
    assert not published_route(b"x" * (MAX_BYTES + 1))


def test_fixture_only_schema_is_explicitly_research_not_original_details():
    mock = {"page": 1, "total": 12, "rows": [
        {"id": "1111111", "cell": ["First example", "Buyer"]},
        {"id": "2222222", "cell": ["Second example", "Buyer"]},
    ]}
    count, keys, shapes = parse_public_json(
        json.dumps(mock).encode("utf-8"), "application/json; charset=utf-8",
    )
    assert count == 2
    assert "rows" in keys
    assert shapes[0][0] == "object"
    # Example fixtures say NOTHING about actual upstream procurement IDs.
    assert "cell" in shapes[0][1]


@pytest.mark.parametrize("body,mime", [
    (b"", "application/json"),
    (b"<html>login</html>", "text/html"),
    (b"{bad}", "application/json"),
    (b"[]", "application/json"),
    (b'{"rows":[]}', "application/json"),
    (b'{"rows":[{"id":"one"}]}', "application/json"),
    (b'{"rows":[1,2]}', "application/json"),
    (b'{"rows":[{},{}]}', "application/json"),
    (b'{"rows":[["one"],["two"]]}', "application/json"),
    (b'{"rows":[{"id": "a"},{"id":"b"}]}', "text/html"),
    (json.dumps({"rows": [{"id": str(n)} for n in range(LIMIT + 1)]}).encode(),
     "application/json"),
])
def test_unknown_login_unbounded_or_one_record_never_counts(body, mime):
    with pytest.raises(ValueError):
        parse_public_json(body, mime)


def test_observed_official_items_totalrows_page_schema_is_accepted_research_only():
    government_grid = {
        "items": [
            {"number": "000001", "name": "Example A", "uchr_sname": "School A"},
            {"number": "000002", "name": "Example B", "uchr_sname": "School B"},
        ],
        "page": 1,
        "totalRows": 2,
        "totalAmount": 1200,
    }
    count, keys, shapes = parse_public_json(
        json.dumps(government_grid).encode("utf-8"), "application/json",
    )
    assert count == 2
    assert "items" in keys and "totalRows" in keys
    assert all(kind == "object" for kind, _ in shapes)


@pytest.mark.parametrize("bad", [
    {"items": [{"id": "one"}, {"id": "two"}], "page": 1, "totalRows": 0},
    {"items": [{"id": "one"}, {"id": "two"}], "page": 1, "totalRows": "2"},
    {"items": [{"id": "one"}, {"id": "two"}], "page": -1, "totalRows": 2},
    {"items": [{"id": "one"}, {"id": "two"}], "page": "1", "totalRows": 2},
    {"items": [{"id": "one"}], "page": 1, "totalRows": 2},
    {"items": [{"id": "one"}, {"id": "two"}] * (LIMIT + 1), "page": 1, "totalRows": 20},
])
def test_observed_official_items_schema_fails_closed_on_incomplete_pagination(bad):
    with pytest.raises(ValueError):
        parse_public_json(json.dumps(bad).encode(), "application/json")
