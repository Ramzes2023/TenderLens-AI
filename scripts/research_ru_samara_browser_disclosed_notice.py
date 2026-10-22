"""Research-only: official Samara-listed notice route in same anonymous browser.

Never counts a real public JSON listing alone as an independent verified card.
No login, authentication bypass, proxy, TLS relaxation, guessed notice IDs,
production activation, or subscriber messages.
"""
from __future__ import annotations

import asyncio

from scripts.research_ru_samara_browser_originals import observe


def main() -> int:
    try:
        status = asyncio.run(observe(disclosed_notice_route=True))
    except Exception as exc:
        print("RU_SAMARA_DISCLOSED_BROWSER_BLOCKED=" + type(exc).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_SAMARA_DISCLOSED_BROWSER_DETAILS=" + (
        "TWO_INDEPENDENT_VERIFIED" if status == 0 else "BLOCKED"
    ))
    print("PRODUCTION_CHANGED=NO")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
