"""Read-only first-party Samara grid/JSON transport diagnostic (research only).

Its purpose is to distinguish failure of the publisher HTML, anonymous
anti-CSRF token, native JSON POST, and independently authenticated native
list rows. Source-ready is ALWAYS false: individual original details are
not verified by this diagnostic.

No credentials, auth bypass, session replay beyond anonymous public grid,
TLS weakening, proxies, fallback mirrors, customer writes or outgoing alerts.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client
from app.sources.ru_samara_public_list import (
    GRID, JSON_URL, HOST, MAX_BYTES, PAGE_SIZE,
    parse_public_list, public_settings, public_token,
)


@dataclass(frozen=True)
class Snapshot:
    stage: str
    category: str
    verified_list_rows: int = 0


def classify(error: BaseException) -> str:
    if isinstance(error, ConnectorTransportError):
        reason = getattr(error, "reason", "policy")
        return reason if reason in {
            "network", "public_ip", "tls_certificate", "http_status",
            "http_transient", "response_size", "policy",
        } else "unclassified"
    if isinstance(error, ValueError):
        return "official_contract"
    return "unclassified"


async def inspect() -> Snapshot:
    stage = "OFFICIAL_GRID_GET"
    try:
        with bounded_fetch(FetchPolicy(frozenset({HOST}), 2, max_bytes=MAX_BYTES)):
            async with source_client(
                timeout=25, trust_env=False, follow_redirects=False,
                headers={"Accept":"text/html", "User-Agent":"Mozilla/5.0"},
            ) as client:
                public = await client.get(GRID)
                public.raise_for_status()
                if "html" not in public.headers.get("content-type", "").lower():
                    raise ValueError("HTML grid required")
                stage = "ANONYMOUS_ORIGINAL_GRID_TOKEN"
                token = public_token(public.content)
                stage = "FIRSTPARTY_NOTICESJSON_POST"
                response = await client.post(
                    JSON_URL, json={"settings": public_settings()},
                    headers={
                        "Accept":"application/json, text/javascript",
                        "X-Requested-With":"XMLHttpRequest",
                        "Referer":GRID,
                        "RequestVerificationToken":token,
                    },
                )
                response.raise_for_status()
                if "json" not in response.headers.get("content-type","").lower():
                    raise ValueError("Actual native JSON required")
                stage = "NATIVE_LIST_CANONICAL_IDENTITIES"
                notices = parse_public_list(response.json(), limit=PAGE_SIZE)
                return Snapshot(stage="NATIVE_LIST_CANONICAL_IDENTITIES",
                                category="visible_unverified_detail",
                                verified_list_rows=len(notices))
    except (ConnectorTransportError, ValueError) as exc:
        return Snapshot(stage=stage, category=classify(exc))
    except Exception:
        # Do not serialize raw exception, DNS, private IP, headers or tokens.
        return Snapshot(stage=stage, category="unclassified")


def main() -> int:
    result = asyncio.run(inspect())
    print("RU_SAMARA_NATIVE_DIAGNOSTIC=" + json.dumps({
        "stage": result.stage,
        "category": result.category,
        "official_native_list_rows": result.verified_list_rows,
    }, sort_keys=True))
    print("PUBLIC_FIRSTPARTY_ORIGINAL_DETAILS=NOT_VERIFIED")
    print("CURRENT_OPEN_SUBMISSION_DEADLINES=NOT_VERIFIED")
    print("FENCED_WORKER_SQL_PUBLIC_SEARCH=NOT_VERIFIED")
    print("PRODUCTION_CHANGED=NO")
    print("RELEASE_READY=NO")
    return 0  # Research CI visibility, not a source activation gate.


if __name__ == "__main__":
    raise SystemExit(main())
