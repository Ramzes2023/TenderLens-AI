"""Read-only original Dagestan public notices export availability check.

No invented tenders or external source parsing, no credentials/proxy/captcha.
Success is discovery only and NOT proof of source integration.
"""
import asyncio
import httpx

from app.sources.http import FetchPolicy, bounded_fetch, source_client, ConnectorTransportError

HOST = "goszakaz.e-dag.ru"
URL = "https://goszakaz.e-dag.ru/smallpurchases/GzwSP/NoticesExport"
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
            kind = (
                "XLSX" if raw.startswith(bytes.fromhex("504b0304")) else
                "XLS" if raw.startswith(bytes.fromhex("d0cf11e0a1b11ae1")) else
                "CSV" if "csv" in mime and bool(raw) else
                "UNVERIFIED"
            )
            print("RU_DAG_EXPORT_FORMAT=" + kind)
            print("RU_DAG_EXPORT_BYTES=" + str(len(raw)))
            print("PRODUCTION_CHANGED=NO")
            return 0 if kind in {"XLSX", "XLS", "CSV"} else 2


def main():
    try:
        return asyncio.run(inspect())
    except (ValueError, httpx.HTTPError, ConnectorTransportError, OSError, TimeoutError) as error:
        print("RU_DAG_EXPORT=BLOCKED_" + type(error).__name__)
        if isinstance(error, ConnectorTransportError):
            print("RU_DAG_EXPORT_RETRYABLE=" + str(error.retryable))
        print("PRODUCTION_CHANGED=NO")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
