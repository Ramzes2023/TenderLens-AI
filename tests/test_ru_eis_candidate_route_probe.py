"""Offline contracts for strictly pinned, operator-only EIS RSS candidates."""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest

from scripts.ru_eis_candidate_route_probe import (
    PATHS, candidate_url, active_official_count,
)


@pytest.mark.parametrize("source,expected", [("eis", "fz44"), ("eis_223", "fz223")])
@pytest.mark.parametrize("path", PATHS)
def test_both_paths_use_exact_official_site_and_exclusive_law(source, expected, path):
    url = urlsplit(candidate_url(source, path))
    q = parse_qs(url.query)
    other = "fz223" if expected == "fz44" else "fz44"
    assert url.scheme == "https" and url.netloc == "zakupki.gov.ru"
    assert url.path == path and not url.fragment
    assert q[expected] == ["on"] and other not in q


@pytest.mark.parametrize("source,path", [
    ("eis_44_html", PATHS[0]), ("eis_223", "/wrong/rss"),
    ("eis", "/epz/order/extendedsearch/rss.xml"),
    ("eis", "/epz/order/extendedsearch/rss/"),
])
def test_cannot_select_unapproved_route_or_source(source, path):
    with pytest.raises(ValueError):
        candidate_url(source, path)


@dataclass
class Notice:
    source: str
    tender_number: str
    external_id: str
    url: str
    deadline: str


@pytest.mark.parametrize("source,num,path", [
    ("eis", "0316300145126000012",
     "/epz/order/notice/ea44/view/common-info.html"),
    ("eis_223", "32616521305",
     "/223/purchase/public/purchase/info/common-info.html"),
])
def test_real_candidate_requires_official_identity_and_future_deadline(source, num, path):
    now = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
    valid = Notice(
        source, num, num,
        "https://zakupki.gov.ru" + path + "?regNumber=" + num,
        "10.12.2026 19:45",
    )
    wrong = replace(valid, url=valid.url.replace("zakupki.gov.ru", "fake.invalid"))
    wrong_law = replace(valid, source="eis_223" if source == "eis" else "eis")
    expired = replace(valid, deadline="01.01.2026 09:00")
    assert active_official_count([valid, wrong, wrong_law, expired], source, now) == 1
    assert active_official_count([wrong, expired], source, now) == 0
