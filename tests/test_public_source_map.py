"""Map is an honest interactive region navigator, not invented location/uptime data."""
from pathlib import Path
from app.api.landing import landing_html
from app.api.public_locale import COPY

ROOT=Path(__file__).resolve().parents[1]


def test_source_map_buttons_drive_actual_list_filter():
    html=landing_html()
    js=(ROOT/"app/api/static/market_directory.js").read_text(encoding="utf-8")
    css=(ROOT/"app/api/static/market_depth.css").read_text(encoding="utf-8")
    for key in ["all","russia","cis","europe","asia","americas","africa","oceania","other"]:
        assert f'data-map-region="{key}"' in html
        assert f'<option value="{key}">' in html
    assert 'aria-pressed="true"' in html
    assert "regionOf(item)" in js
    assert "button.addEventListener('click'" in js
    assert "root.querySelector('#sourceDirectoryStatus').scrollIntoView" in js
    assert ".source-map-nav" in css
    assert "Decorative graticule" in css
    assert "Regions are navigational filters, not proof of source activity." in COPY
    assert 'id="sourceDirectory"' in html


def test_public_map_has_no_external_map_dependency_or_unverified_success():
    js=(ROOT/"app/api/static/market_directory.js").read_text(encoding="utf-8")
    assert "googleapis.com" not in js
    assert "mapbox" not in js.lower()
    assert "live_status" not in js
    assert "source-directory.json" in js
