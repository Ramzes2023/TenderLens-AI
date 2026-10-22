"""Read-only Chechnya procurement publisher/ETP reachability discovery.

These are two fixed PUBLIC historical discovery endpoints, NOT an EIS RSS
replacement and NOT a current or queryable procurement feed. Neither result
can ever satisfy Chechnya EIS Worker/SQLite/Telegram release acceptance.
No cookies, redirects, private IPs, secrets, or production writes.
"""
from __future__ import annotations

import asyncio
import html
import json
import re

from app.sources.http import FetchPolicy, bounded_fetch, source_client

TARGETS = {
    "official_committee_information": (
        "https://www.gostorgi-chr.ru/mun-order/",
        "www.gostorgi-chr.ru",
    ),
    "fabrikant_historical_public_example": (
        "https://soap4.fabrikant.ru/44/ea21/procedure/view/1184531/?printVersion=1",
        "soap4.fabrikant.ru",
    ),
}
MAX_BYTES = 2 * 1024 * 1024


def classify_public_page(target: str, status: int, content_type: str, payload: bytes) -> str:
    """Classify evidence conservatively; never promote HTML into a tender."""
    if status != 200:
        return "HTTP_NOT_PUBLIC_OR_UNAVAILABLE"
    if len(payload) > MAX_BYTES:
        return "RESPONSE_OVER_LIMIT"
    if "html" not in content_type.lower():
        return "NON_HTML_RESPONSE"
    # These pages are HTML and can include nested formatting, so normalize
    # tag boundaries while preventing a captcha/login page from being counted.
    text = html.unescape(re.sub(r"<[^>]*>", " ", payload.decode("utf-8", errors="replace")))
    text = " ".join(text.split()).casefold()
    if "captcha" in text or "вход в систему" in text or "авторизация" in text:
        return "AUTH_OR_CHALLENGE_PAGE"
    if target == "official_committee_information":
        if "комитет правительства чеченской республики" in text:
            return "OFFICIAL_INFORMATION_PAGE_ONLY_NO_TENDER_FEED"
    elif target == "fabrikant_historical_public_example":
        if ("goszakaz@gostorgi-chr.ru" in text
                and re.search(r"44\s*[-–]?\s*фз", text)):
            return "HISTORICAL_PUBLIC_ETP_EXAMPLE_ONLY_NO_DISCOVERY_FEED"
    return "INSUFFICIENT_PUBLISHER_EVIDENCE"


async def probe_one(name: str, url: str, host: str) -> dict[str, str]:
    result = {"target": name, "state": "UNVERIFIED", "counts_as_live_source": "NO"}
    try:
        # The bounded client validates HTTPS and DNS resolves only to global
        # public addresses; the host is an exact allowlist with no redirects.
        with bounded_fetch(FetchPolicy(frozenset({host}), 1, max_bytes=MAX_BYTES)):
            async with source_client(
                timeout=10, verify=True, trust_env=False,
                follow_redirects=False,
                headers={"User-Agent": "VALYQON-public-source-diagnostic/1.0"},
            ) as client:
                response = await client.get(url)
                result["state"] = classify_public_page(
                    name,
                    response.status_code,
                    response.headers.get("content-type", ""),
                    response.content,
                )
    except Exception as error:
        # Bounded client exceptions can include signed/request URLs. Only
        # stable error *classes*, never repr/message/IP/body, are disclosed.
        name_of_error = type(error).__name__
        result["state"] = (
            "NETWORK_OR_TLS_UNAVAILABLE"
            if name_of_error in {"ConnectorTransportError", "ConnectError", "ConnectTimeout", "ReadTimeout"}
            else "SAFE_PROBE_ERROR"
        )
    return result


async def probe_all() -> list[dict[str, str]]:
    results = []
    for name, (url, host) in TARGETS.items():
        results.append(await probe_one(name, url, host))
    return results


def main() -> int:
    for result in asyncio.run(probe_all()):
        print("RU_CHECHNYA_ALTERNATIVE_PUBLIC_SIGNAL=" + json.dumps(result, sort_keys=True))
    print("RU_CHECHNYA_ALTERNATIVES_ARE_NOT_EIS_OR_RELEASE_EVIDENCE=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
