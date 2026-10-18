"""Hosted read-only first-party Kavkaz.RF parser/transport diagnosis.

Source fixtures do not satisfy the real procurement acceptance gate.
"""
import asyncio

from app.sources.kavkaz_rf_firstparty import KavkazRfFirstpartySource
from app.sources.http import ConnectorTransportError


def main():
    try:
        notices = asyncio.run(KavkazRfFirstpartySource().fetch(2))
        if len(notices) != 2 or len({n.external_id for n in notices}) != 2:
            raise ValueError("Two unique current first-party original details required")
        print("RU_KAVKAZ_DIAGNOSTIC=LIVE_TWO_ORIGINALS")
        print("RU_KAVKAZ_LIVE_VERIFIED=" + str(len(notices)))
        print("PRODUCTION_CHANGED=NO")
        return 0
    except (ValueError, ConnectorTransportError, OSError, TimeoutError) as exc:
        print("RU_KAVKAZ_DIAGNOSTIC=BLOCKED_" + type(exc).__name__)
        # ValueError messages here are our audited parser constants only,
        # not returned remote HTML, URL, tenant content or secrets.
        if isinstance(exc, ValueError):
            print("RU_KAVKAZ_PARSER_GATE=" + str(exc)[:160])
        if isinstance(exc, ConnectorTransportError):
            print("RU_KAVKAZ_RETRYABLE=" + str(exc.retryable))
        print("PRODUCTION_CHANGED=NO")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
