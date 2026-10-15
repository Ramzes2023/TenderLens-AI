"""Explicit, isolated TED live -> worker -> SQLite -> searchable catalog acceptance.

No production configuration, account, AWS access, credentials or customer data.
Only --live contacts the official TED API through the existing strict transport.
Output is structural status/counts only, not tender text or URLs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.backend import database_for
from app.sources.catalog import SourceCatalog
from app.sources.ingestion import (
    ConnectorSyncHandler,
    SYSTEM_SCOPE,
    connector_version,
    sync_window,
)
from app.sources.multi import MultiSourceFetcher
from app.sources.opportunities import OpportunityRepository
from app.sources.registry import SourceRegistration, SourceRegistry
from app.sources.snapshots import snapshot_catalog
from app.sources.ted_api import TedApiSource

SOURCE_ID = "ted"
MAX_NOTICES = 5


class AcceptanceFailure(RuntimeError):
    """An acceptance condition was not met (never include upstream content)."""


def require(condition: bool, stage: str) -> None:
    if not condition:
        raise AcceptanceFailure(stage)


def catalog_for(source: object) -> SourceCatalog:
    registry = SourceRegistry(
        [SourceRegistration(
            key=SOURCE_ID,
            display_name="Tenders Electronic Daily",
            source=source,
            jurisdictions=("EU",),
            homepage_url="https://ted.europa.eu/",
            official=True,
        )]
    )
    return SourceCatalog(registry, MultiSourceFetcher(registry, concurrency=1))


def accept(source: object) -> dict[str, object]:
    """Exercise production worker and catalog over a new disposable SQLite DB.

    For a live proof, the caller MUST provide the real TedApiSource. Unit tests
    deliberately inject a stub and never claim that their data is live.
    """
    with TemporaryDirectory(prefix="valyqon-ted-gate-") as directory:
        database = database_for(Path(directory) / "only-this-test.sqlite3")
        try:
            opportunities = OpportunityRepository(database)
            opportunities.initialize()
            catalog = catalog_for(source)
            payload = {
                "schema": 1,
                "source_id": SOURCE_ID,
                "sync_window": sync_window(),
                "connector_version": connector_version(SOURCE_ID),
            }
            context = SimpleNamespace(
                job=SimpleNamespace(scope=SYSTEM_SCOPE),
                should_stop=False,
            )
            result = ConnectorSyncHandler(
                catalog, opportunities, max_records=MAX_NOTICES
            )(context, payload)
            accepted = result["accepted_count"]
            require(0 < accepted <= MAX_NOTICES, "NO_ACCEPTED_NOTICES")
            require(
                result["fetched_count"] >= accepted
                and result["skipped_count"] == 0,
                "INCOMPLETE_NORMALIZATION",
            )

            persisted = opportunities.read(SOURCE_ID, limit=MAX_NOTICES)
            require(len(persisted) == accepted, "PERSISTENCE_COUNT_MISMATCH")
            require(
                len({notice.identity for notice in persisted}) == accepted,
                "PERSISTENCE_DUPLICATES",
            )
            for notice in persisted:
                expected = (
                    "https://ted.europa.eu/en/notice/-/detail/"
                    + quote(notice.external_id, safe="-")
                )
                require(
                    notice.source == SOURCE_ID
                    and notice.external_id.strip()
                    and notice.tender_number == notice.external_id
                    and notice.url == expected
                    and notice.title.strip()
                    and not notice.title.startswith("TED notice "),
                    "NON_AUTHORITATIVE_NOTICE",
                )

            # Real user-supplied string routed through existing snapshot catalog.
            # Exact title is used to avoid guessing language/tokenization.
            sample = persisted[0]
            report = asyncio.run(
                snapshot_catalog(catalog, opportunities).fetch(
                    limit_per_source=MAX_NOTICES,
                    source_keys=(SOURCE_ID,),
                    search_terms=(sample.title,),
                )
            )
            require(not report.failures, "SNAPSHOT_SEARCH_FAILED")
            require(
                any(notice.identity == sample.identity
                    and notice.url == sample.url
                    for notice in report.notices),
                "SEARCH_NOT_FOUND",
            )
            no_match = asyncio.run(
                snapshot_catalog(catalog, opportunities).fetch(
                    limit_per_source=MAX_NOTICES,
                    source_keys=(SOURCE_ID,),
                    search_terms=("valyqon-unmatchable-176-aa91519d",),
                )
            )
            require(
                not no_match.failures and not no_match.notices,
                "SEARCH_FALSE_POSITIVE",
            )
            require(
                not opportunities.read("eis", limit=MAX_NOTICES),
                "CROSS_SOURCE_LEAK",
            )
            require(
                opportunities.upsert(sample, connector_version(SOURCE_ID)) is False
                and len(opportunities.read(SOURCE_ID, limit=MAX_NOTICES)) == accepted,
                "UPSERT_NOT_IDEMPOTENT",
            )

            return {
                "source": SOURCE_ID,
                "normalized": accepted,
                "persisted": len(persisted),
                "searched": len(report.notices),
                "official_identity": "VERIFIED",
                "snapshot_search": "VERIFIED",
                "cross_source_isolation": "VERIFIED",
                "idempotent_upsert": "VERIFIED",
                "database": "ephemeral-sqlite",
                "full_pdf_analysis": False,
                "authenticated_browser_test": False,
            }
        finally:
            database.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicitly fetch actual anonymous TED tenders via bounded HTTPS",
    )
    args = parser.parse_args(argv)
    if not args.live:
        print(json.dumps({
            "status": "NOT_RUN",
            "reason": "LIVE_OPT_IN_REQUIRED",
            "outbound_calls": 0,
        }, sort_keys=True))
        return 2
    try:
        evidence = accept(TedApiSource(timeout=15))
    except Exception as error:
        # No raw vendor exception strings, URLs, query text or secrets in CI.
        print(json.dumps({
            "status": "FAIL",
            "stage": (
                str(error) if isinstance(error, AcceptanceFailure)
                else type(error).__name__
            ),
            "source": SOURCE_ID,
        }, sort_keys=True))
        return 1
    print(json.dumps({
        "status": "LIVE_VERIFIED",
        **evidence,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
