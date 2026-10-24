"""GPB public route discovery cannot infer real tenders or cross-host redirects."""
import pytest

from scripts.research_ru_gpb_public_route_recovery import (
    first_party_numeric_links, LISTINGS, HOSTS,
)


def test_firstparty_numeric_and_slugged_routes_are_both_detected_without_external():
    original = (b'<html><a href="/procedures/etp/1240053/">one</a>'
                b'<a href="https://new.etpgpb.ru/procedures/etp/1210002-ap113482/">two</a>'
                b'<a href="https://attacker.example/procedures/etp/22222/">bad</a>'
                b'<a href="/procedures/etp/1000000/?token=hidden">bad</a>'
                b'<a href="/procedures/etp/1240053/">duplicate</a></html>')
    assert first_party_numeric_links(original, LISTINGS[0]) == ("1210002", "1240053")


def test_no_real_original_details_are_assumed_from_index_numbers():
    assert first_party_numeric_links(b"<html><h1>Procurement</h1></html>", LISTINGS[0]) == ()
    for bad in (b"", b"data\x00", b"<script>" + b"x" * 1_800_001 + b"</script>"):
        with pytest.raises(ValueError):
            first_party_numeric_links(bad, LISTINGS[0])
    with pytest.raises(ValueError):
        first_party_numeric_links(b"<a href='/procedures/etp/1240053/'>x</a>", "http://etpgpb.ru/procedures/")
    assert HOSTS == ("etpgpb.ru", "new.etpgpb.ru")
