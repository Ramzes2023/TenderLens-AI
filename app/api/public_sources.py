"""Public, read-only metadata of registered tender source adapters.

No private credentials, probe claims, or inferred uptime numbers are exposed.
"""
from __future__ import annotations
from urllib.parse import urlsplit


# Implemented in main but gated behind optional operator settings.
# This is an informational inventory, NOT the runtime registry or live health.
# Keep keys, titles, transports and official URLs aligned with app/sources/catalog.py.
_RU_OPT_IN_ADAPTERS = (
    ("eis_223", "EIS 223-FZ", "rss", True, "general", "https://zakupki.gov.ru/"),
    ("b2b_center", "B2B-Center", "html", False, "general", "https://www.b2b-center.ru/"),
    ("mikroton_tender", "MikroTon Tender — public procurement API", "api", False, "general", "https://tender.mt52.ru/"),
    ("tektorg", "TEK-Torg — public tenders (law not independently verified)", "html", False, "general", "https://www.tektorg.ru/223-fz/procedures"),
    ("eis_44_html", "EIS 44-FZ — experimental public listing (detail unverified)", "html", True, "general", "https://zakupki.gov.ru/"),
    ("lenobl_small_public", "Leningrad Oblast official public small-purchase requests", "html", True, "regional_small", "https://zakupki.lenreg.ru/Search/NewRequests"),
    ("stan_commercial_public", "STAN-Torgi — genuine commercial procurement procedures", "html", False, "general", "https://stantorgi.ru/etp"),
    ("nmck_native_public", "NMCK — first-party public small-purchase notices", "html", False, "regional_small", "https://xn--j1adc1b.xn--p1ai/procedures"),
    ("gpb_etp_public", "Gazprombank ETP public procurement (law unverified)", "html", False, "general", "https://etpgpb.ru/procedures/"),
)


def source_directory(catalog):
    registry = getattr(catalog, "registry", None)
    if registry is None:
        return {"sources": [], "source_count": 0, "enabled_count": 0,
                "optional_sources": [], "optional_count": 0,
                "scope": "current_runtime_registry", "live_health_verified": False}
    sources = []
    for m in registry.metadata():
        url = m.homepage_url or ""
        parsed = urlsplit(url)
        safe_url = url if parsed.scheme == "https" and parsed.hostname and not (parsed.username or parsed.password) else None
        jurisdictions = list(m.jurisdictions)
        country = jurisdictions[0] if jurisdictions else "GLOBAL"
        if country == "RU":
            region = "russia"
        elif country in {"KZ", "KG", "AZ", "AM", "BY", "MD", "TJ", "UZ", "GE"}:
            region = "cis"
        else:
            region = "world"
        name = m.display_name
        key = m.key
        # This is an editorial categorization, not a proof of a procurement law,
        # published bid limit, or current availability.
        small = any(part in (key + " " + name).lower()
                    for part in ("small", "regional", "lenobl", "nmck", "municipal"))
        sources.append({
            "key": key, "name": name, "country": country,
            "region": region, "transport": m.transport.value,
            "official": bool(m.official), "enabled": bool(m.enabled),
            "requires_credentials": bool(m.capabilities.authentication_required),
            "focus": "regional_small" if small else "general",
            "homepage": safe_url,
            "live_status": "not_verified",
        })
    sources.sort(key=lambda item: (
        0 if item["region"] == "russia" else 1 if item["region"] == "cis" else 2,
        item["country"], item["name"].casefold(), item["key"]
    ))
    # Keep optional connectors separate: users must never mistake an adapter
    # present in code for one installed, enabled, or delivering live tenders.
    registered_keys = {item["key"] for item in sources}
    optional_sources = [
        {
            "key": key, "name": name, "country": "RU", "region": "russia",
            "transport": transport, "official": official, "enabled": False,
            "registered": False, "requires_credentials": False,
            "focus": focus, "homepage": homepage, "live_status": "not_verified",
        }
        for key, name, transport, official, focus, homepage in _RU_OPT_IN_ADAPTERS
        if key not in registered_keys
    ]
    return {
        "sources": sources, "source_count": len(sources),
        "optional_sources": optional_sources, "optional_count": len(optional_sources),
        "enabled_count": sum(int(x["enabled"]) for x in sources),
        "scope": "current_runtime_registry",
        "live_health_verified": False,
        "note": "Registered means present in the running catalog. Optional sources only indicate adapters available in this codebase. Neither proves live tender delivery.",
    }
