"""Public source inventory derived from the configured runtime registry, never a live claim."""
from __future__ import annotations

from html import escape
from urllib.parse import urlsplit


_REGION_CODES = {
    "Russia": {"RU"},
    "CIS & Caucasus": {"AZ", "AM", "BY", "KZ", "KG", "MD", "TJ", "UZ", "GE"},
    "Europe": {"EU", "GB", "UK", "FR", "DE", "IT", "ES", "NL", "NO", "SE", "CH"},
    "Asia & Middle East": {"AE", "HK", "JP", "SG", "IN", "TR", "CN", "KR", "SA", "QA"},
    "Americas": {"US", "CA", "BR", "MX"},
    "Africa": {"ZA", "NG", "KE", "EG"},
    "Oceania": {"AU", "NZ"},
}
GROUPS = tuple(_REGION_CODES) + ("Global & other",)


def _region(codes):
    jurisdictions = set(codes or ())
    for name, region in _REGION_CODES.items():
        if jurisdictions & region:
            return name
    return "Global & other"


def _registrations(runtime):
    catalog = getattr(runtime, "source_catalog", None)
    registry = getattr(catalog, "registry", None)
    if registry is None:
        return ()
    return registry.registrations()


def source_directory_html(runtime) -> str:
    """Always enumerate actual in-memory registrations, never unmerged PRs or files."""
    registrations = _registrations(runtime)
    groups = {group: [] for group in GROUPS}
    for item in registrations:
        if not item.key or not item.display_name:
            continue
        groups[_region(item.jurisdictions)].append(item)
    count = sum(len(entries) for entries in groups.values())
    enabled = sum(bool(item.enabled) for entries in groups.values() for item in entries)
    filters = '<button type="button" class="coverage-filter is-selected" data-coverage-region="all" aria-pressed="true">All regions</button>'
    for group in GROUPS:
        if not groups[group]:
            continue
        filters += (
            '<button type="button" class="coverage-filter" data-coverage-region="' +
            escape(group, quote=True) + '" aria-pressed="false">' + escape(group) +
            ' <span aria-hidden="true">' + str(len(groups[group])) + '</span></button>'
        )
    blocks = []
    for group, items in groups.items():
        if not items:
            continue
        cards = []
        for item in sorted(items, key=lambda value: (not value.enabled, value.display_name.casefold())):
            name = escape(item.display_name)
            key = escape(item.key)
            country = escape(", ".join(item.jurisdictions) or "Global")
            category = "Public agency" if item.official else "Commercial platform"
            # This is configuration metadata, NOT proof of a recent tender or a successful request.
            state = "Configured adapter" if item.enabled else "Disabled / setup required"
            if item.capabilities.authentication_required and not item.enabled:
                state = "Access configuration required"
            external = ""
            if item.homepage_url:
                parsed = urlsplit(item.homepage_url)
                if parsed.scheme == "https" and parsed.hostname:
                    external = '<a href="' + escape(item.homepage_url, quote=True) + '" rel="noopener noreferrer" target="_blank">Official source ↗</a>' if item.official else '<a href="' + escape(item.homepage_url, quote=True) + '" rel="noopener noreferrer" target="_blank">Source website ↗</a>'
            cards.append(
                '<article class="coverage-card" data-source-key="' + key +
                '" data-source-search="' + escape((item.display_name + " " + item.key + " " + " ".join(item.jurisdictions)).casefold(), quote=True) + '">' +
                '<div class="coverage-card-top"><span class="coverage-country">' + country +
                '</span><span class="coverage-state" data-state="' + ("configured" if item.enabled else "disabled") + '">' +
                escape(state) + '</span></div><h4>' + name + '</h4><p>' + escape(category) + ' · ' +
                escape(str(item.transport).replace("SourceTransport.", "").upper()) +
                '</p><div class="coverage-card-foot"><small>Registered adapter · live status unverified</small>' +
                external + '</div></article>'
            )
        blocks.append(
            '<section class="coverage-group" data-coverage-group="' + escape(group, quote=True) + '">'
            '<div class="coverage-group-heading"><h3>' + escape(group) + '</h3><span>' +
            str(len(items)) + ' registered adapters</span></div><div class="coverage-cards">' +
            ''.join(cards) + '</div></section>'
        )
    if not count:
        blocks.append(
            '<div class="coverage-empty"><h3>Source inventory unavailable in this session</h3>'
            '<p>The runtime registry has not loaded. No sources are claimed active.</p></div>'
        )
    return (
        '<section id="coverage" class="content-section coverage-section coverage-explorer">'
        '<div class="coverage-intro"><span class="eyebrow">SOURCE COVERAGE · VERIFIED METADATA ONLY</span>'
        '<h2>Explore procurement beyond the obvious.</h2>'
        '<p>From international portals to Russia’s regional, smaller and commercial procurement '
        'landscape, VALYQON is developing a deeper source map. Explore adapters registered in '
        'this server build, with their configuration clearly distinguished from live delivery.</p>'
        '<div class="coverage-principles"><span>Market depth</span><span>Transparent evaluation</span>'
        '<span>Source verification</span></div></div>'
        '<div class="coverage-explorer-panel"><div class="coverage-explorer-heading">'
        '<div><span class="eyebrow">LIVE REGISTRY INVENTORY</span>'
        '<h3>Source directory</h3><p>No arbitrary marketing total. Every card comes from '
        'the application registry; not all adapters are enabled or reachable.</p></div>'
        '<div class="coverage-metrics"><div><strong>' + str(count) +
        '</strong><small>Registered adapters</small></div><div><strong>' + str(enabled) +
        '</strong><small>Enabled in this environment (not live-verified)</small></div></div></div>'
        '<div class="coverage-controls"><label for="coverageSearch">Find a source '
        '<input id="coverageSearch" type="search" placeholder="Name, country or source code" '
        'autocomplete="off" maxlength="100"></label><div class="coverage-regions" '
        'role="group" aria-label="Filter sources by region">' + filters + '</div></div>'
        '<div class="coverage-map" aria-hidden="true"><div class="coverage-globe"></div>'
        '<span class="coverage-map-caption">RUSSIA · CIS · GLOBAL MARKETS</span></div>'
        '<p class="coverage-counter" id="coverageCounter" aria-live="polite">'
        'Browse the registered source inventory</p><div id="coverageResults">' +
        ''.join(blocks) + '</div><p id="coverageNoMatches" hidden>No sources match these filters.</p>'
        '<div class="coverage-proof"><strong>What the labels mean</strong><p>'
        'Configured adapter ≠ successful retrieval. Live availability, tender completeness and '
        'daily freshness must be checked against actual source observations. No comparison with '
        'competitor databases is claimed.</p><a href="/status">Current service status ↗</a>'
        '<a href="/scoring-methodology">Read scoring methodology ↗</a></div>'
        '</div></section>'
    )
