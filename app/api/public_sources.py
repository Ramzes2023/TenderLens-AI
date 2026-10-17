"""Public, read-only metadata of registered tender source adapters.

No private credentials, probe claims, or inferred uptime numbers are exposed.
"""
from __future__ import annotations
from urllib.parse import urlsplit


def source_directory(catalog):
    registry = getattr(catalog, "registry", None)
    if registry is None:
        return {"sources": [], "source_count": 0, "enabled_count": 0,
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
    return {
        "sources": sources, "source_count": len(sources),
        "enabled_count": sum(int(x["enabled"]) for x in sources),
        "scope": "current_runtime_registry",
        "live_health_verified": False,
        "note": "Enabled means allowed by configuration; it does not prove a successful upstream fetch.",
    }
