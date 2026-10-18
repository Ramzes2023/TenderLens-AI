"""Offline hostile RSS cases are NOT evidence of live available procurement."""
import pytest
from scripts.research_ru_gpb_current_rss import (
    feed_originals, FEED, FEED_HOST, DETAIL_HOST,
)


def rss(first="https://etpgpb.ru/procedures/etp/123456-a/",
        second="https://etpgpb.ru/procedures/etp/123457-b/"):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<item><title>Поставка специального оборудования</title><link>{first.replace("&", "&amp;")}</link></item>
<item><title>Оказание услуг по обслуживанию</title><link>{second.replace("&", "&amp;")}</link></item>
</channel></rss>""".encode("utf-8")


def test_two_independent_official_rss_original_links():
    verified = feed_originals(rss())
    assert [v[0] for v in verified] == ["123456", "123457"]
    assert all(v[2].startswith("https://etpgpb.ru/procedures/etp/") for v in verified)


@pytest.mark.parametrize("bad", [
    "http://etpgpb.ru/procedures/etp/123456-a/",
    "https://evil.example/procedures/etp/123456-a/",
    "https://etpgpb.ru.evil.test/procedures/etp/123456-a/",
    "https://etpgpb.ru/procedures/etp/123456-a/?token=secret",
    "https://user:pass@etpgpb.ru/procedures/etp/123456-a/",
    "https://etpgpb.ru/procedures/etp/123456-a/#fragment",
    "https://new.etpgpb.ru/procedures/etp/123456-a/",
])
def test_wrong_first_party_or_unvalidated_detail_host_fails_closed(bad):
    with pytest.raises(ValueError):
        feed_originals(rss(first=bad))


def test_no_fake_green_from_single_duplicate_or_login_payload():
    with pytest.raises(ValueError):
        feed_originals(rss(second="https://etpgpb.ru/procedures/etp/123456-a/"))
    with pytest.raises(ValueError):
        feed_originals(b"<html>Login required</html>")
    with pytest.raises(ValueError):
        feed_originals(b"<rss><channel></channel></rss>")


def test_unsafe_xml_entity_declaration_fails_closed():
    payload = b'<!DOCTYPE rss [<!ENTITY test "fake notice">]><rss><channel></channel></rss>'
    with pytest.raises(ValueError):
        feed_originals(payload)


def test_official_documented_feed_exact_host():
    assert FEED == "https://etpgpb.ru/procedures.rss"
    assert FEED_HOST == "etpgpb.ru"
    assert DETAIL_HOST == "etpgpb.ru"
