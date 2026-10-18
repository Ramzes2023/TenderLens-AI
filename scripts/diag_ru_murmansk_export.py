"""Investigate only the original publicly advertised Murmansk registry export.

This is never a live source acceptance, and never extracts/generates notices.
Bounded to one fixed HTTPS origin, no redirects, cookies, proxies or credentials.
"""
import asyncio
import httpx
from app.sources.http import FetchPolicy, bounded_fetch, source_client, ConnectorTransportError

HOST = "gz-murman.ru"
URL = "https://gz-murman.ru/site/GzwSP/NoticesExport"
MAX_BYTES = 2_000_000


async def inspect():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 1, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=25, trust_env=False, follow_redirects=False,
            headers={"Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/csv",
                     "User-Agent": "Mozilla/5.0"},
        ) as client:
            response = await client.get(URL)
            response.raise_for_status()
            raw = response.content
            mime = response.headers.get("content-type", "").lower().split(";", 1)[0]
            kind = ("XLSX_ZIP" if raw.startswith(b"PK\\x03\\x04") else
                    "XLS_OLD" if raw.startswith(bytes.fromhex("d0cf11e0a1b11ae1")) else
                    "CSV_TEXT" if "csv" in mime and raw else
                    "HTML_OR_UNKNOWN")
            print("RU_MURMANSK_EXPORT_KIND=" + kind)
            print("RU_MURMANSK_EXPORT_BYTES=" + str(len(raw)))
            print("RU_MURMANSK_EXPORT=RESEARCH_ONLY")
            return 0 if kind in {"XLSX_ZIP", "XLS_OLD", "CSV_TEXT"} else 2


def main():
    try:
        return asyncio.run(inspect())
    except (ValueError, ConnectorTransportError, httpx.HTTPError, OSError, TimeoutError) as error:
        print("RU_MURMANSK_EXPORT=BLOCKED_" + type(error).__name__)
        if isinstance(error, ConnectorTransportError):
            print("RU_MURMANSK_EXPORT_RETRYABLE=" + str(error.retryable))
        return 2
    finally:
        print("PRODUCTION_CHANGED=NO")


if __name__ == "__main__":
    raise SystemExit(main())
