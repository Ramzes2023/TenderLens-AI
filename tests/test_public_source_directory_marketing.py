"""Guest marketing coverage uses runtime registry metadata without invented live claims."""
from types import SimpleNamespace

from app.api.landing import landing_html
from app.api.public_source_directory import source_directory_html
from app.api.public_locale import COPY
from app.sources.registry import SourceCapabilities, SourceRegistration, SourceRegistry, SourceTransport


def runtime(registrations):
    return SimpleNamespace(source_catalog=SimpleNamespace(registry=SourceRegistry(registrations)))


def registration(key, title, jurisdiction, *, enabled, official=True, auth=False):
    return SourceRegistration(
        key=key, display_name=title, source=SimpleNamespace(name=key),
        transport=SourceTransport.HTML, jurisdictions=(jurisdiction,),
        languages=("ru",), homepage_url="https://example.org/tender/",
        official=official, enabled=enabled,
        capabilities=SourceCapabilities(authentication_required=auth),
    )


def test_guest_coverage_is_derived_from_registry_and_scoped_to_build():
    r=runtime((
        registration("ru_small_example", "Russian small procurement demo", "RU", enabled=True),
        registration("kz_example", "KZ government demo", "KZ", enabled=False, auth=True),
        registration("eu_demo", "European sample", "EU", enabled=True),
    ))
    html=landing_html(runtime=r)
    assert 'data-source-key="ru_small_example"' in html
    assert 'data-source-key="kz_example"' in html
    assert 'data-coverage-group="Russia"' in html
    assert 'data-coverage-group="CIS &amp; Caucasus"' in html
    assert 'Registered adapter' in html
    assert 'Source verification' in html
    assert "Russian small procurement demo" in html
    assert "Access configuration required" in html
    assert '3</strong><small>Registered adapters' in html
    assert '2</strong><small>Enabled in this environment' in html
    assert 'data-source-key="unmerged_source"' not in html
    assert 'data-public-locale="ru"' in html
    assert '/assets/source_directory.js' in html


def test_preview_disabled_sources_are_not_misrepresented_as_live():
    r=runtime((registration("disabled", "Portal", "RU", enabled=False),))
    html=source_directory_html(r)
    assert "Disabled / setup required" in html
    assert "live status unverified" in html
    assert "No comparison with competitor" in html
    assert "working today" not in html.lower()


def test_no_registry_renders_candid_empty_state():
    html=source_directory_html(SimpleNamespace())
    assert "Source inventory unavailable" in html
    assert "Registered adapters" in html
    assert "<strong>0</strong>" in html


def test_marketing_translations_are_complete_for_new_distinctive_proposition():
    for value in (
        "Find the tenders", "your usual search misses.", "Sources",
        "Look beyond the federal feed.", "Configured adapter",
        "Registered adapter · live status unverified",
        "Source verification", "Russia", "CIS & Caucasus",
    ):
        assert value in COPY
        assert any("а" <= ch.lower() <= "я" for ch in COPY[value])
