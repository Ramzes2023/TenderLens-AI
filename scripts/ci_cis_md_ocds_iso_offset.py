"""Real Moldova MTender OCDS index probe using the documented ISO offset.

Read-only official HTTPS. No redirect, credentials, production or mocks.
Probe tests the API contract discovered in the open-source MTender client:
  GET /tenders/?offset=ISO8601&limit=20 and /tenders/cn?offset=ISO8601&limit=20.
No claim of working tenders until this official request succeeds.
"""
from __future__ import annotations
import json
import re
import ssl
import sys
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

HOST = "public.mtender.gov.md"
BASE = f"https://{HOST}"
MAX_BODY = 512 * 1024
TIMEOUT = 12
OCID = re.compile(r"^ocds-b3wdp1-MD-\d{10,18}$")
PATHS = ("/tenders/", "/tenders/cn")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def official_url(path, offset):
    if path not in PATHS:
        raise ValueError("Unapproved OCDS listing endpoint.")
    if not isinstance(offset, str) or not re.fullmatch(
        r"20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", offset
    ):
        raise ValueError("Unapproved ISO-UTC offset.")
    return BASE + path + "?" + urlencode({"offset": offset, "limit": "20"})


def valid_index(raw):
    if not raw or len(raw) > MAX_BODY:
        return {"verified": False, "reason": "empty_or_oversized"}
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError):
        return {"verified": False, "reason": "invalid_json"}
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return {"verified": False, "reason": "unrecognized_ocds_structure"}
    rows = payload["data"]
    count = sum(
        isinstance(row, dict)
        and isinstance(row.get("ocid"), str)
        and OCID.fullmatch(row["ocid"]) is not None
        and isinstance(row.get("date"), str)
        and row["date"].strip() != ""
        for row in rows[:20]
    )
    return {"verified": count > 0, "kind": "official_ocds_public_index",
            "row_count": len(rows), "complete_ocid_date_rows": count,
            "next_offset_present": isinstance(payload.get("offset"), str)}


def get_probe(path, offset, opener):
    url = official_url(path, offset)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != HOST or parsed.port not in (None, 443):
        raise AssertionError("Official host mismatch.")
    result = {"path": path, "window_start": offset[:10], "verified": False}
    try:
        req = Request(url, headers={"User-Agent": "VALYQON-readonly-MTender-OCDS/1.0",
                                    "Accept": "application/json"})
        with opener.open(req, timeout=TIMEOUT) as response:
            result["status"] = response.status
            if response.status != 200:
                result["reason"] = "unacceptable_status"
                return result
            raw = response.read(MAX_BODY + 1)
            result["bytes"] = len(raw)
            if len(raw) > MAX_BODY:
                result["reason"] = "response_too_large"
                return result
            result.update(valid_index(raw))
    except (HTTPError, URLError, OSError, TimeoutError) as error:
        result["failure_kind"] = type(error).__name__
    return result


def main():
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    now = datetime.now(timezone.utc)
    # MTender is ascending by date and an offset is required for recent notices.
    windows = [(now - timedelta(days=n)).replace(microsecond=0).isoformat()
               for n in (30, 120, 365)]
    results = [get_probe(path, offset, opener) for path in PATHS for offset in windows]
    verified = any(row["verified"] for row in results)
    print(json.dumps({"source": "md_mtender_ocds", "verified": verified,
                      "official_live_index_verified": verified,
                      "production_activation_allowed": False,
                      "storage_and_search_verified": False,
                      "results": results}, ensure_ascii=False, sort_keys=True))
    return 0 if verified else 1


if __name__ == "__main__":
    sys.exit(main())
