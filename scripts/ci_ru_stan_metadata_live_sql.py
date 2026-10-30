"""Strict first-party STAN buyer/deadline persisted-search acceptance.

No fixtures, historic search snippets or synthetic vendor receipts. Any metadata
claimed here must be present in independently verified HTTPS original details.
Only disposable SQLite. Leaves production and source settings unchanged.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.sources.stan_commercial_public import StanCommercialPublicSource
from app.sources.opportunities import OpportunityRepository
from app.sources.ingestion import connector_version

SOURCE = "stan_commercial_public"


def verify():
    notices = asyncio.run(StanCommercialPublicSource(timeout=25).fetch(limit=2))
    # Real official listings may include one commercial procedure among
    # many EIS/223-FZ mirrors. Still require independent first-party detail,
    # buyer and Moscow deadline for EVERY accepted notice, never fixtures.
    if not 1 <= len(notices) <= 2 or len({notice.external_id for notice in notices}) != len(notices):
        raise AssertionError("No independently distinct STAN commercial original")
    # A metadata feature is not accepted on merely the old title-only source.
    buyers = sum(bool(notice.customer) for notice in notices)
    deadlines = sum(bool(notice.deadline) for notice in notices)
    if buyers != len(notices) or deadlines != len(notices):
        raise AssertionError("Original STAN buyers or Moscow bid deadlines not corroborated")
    with tempfile.TemporaryDirectory(prefix="valyqon-ru-stan-metadata-") as root:
        db = Database(DatabaseSettings("ru-stan-metadata-real", Path(root) / "proof.sqlite"))
        try:
            store = OpportunityRepository(db)
            store.initialize()
            for notice in notices:
                if not store.upsert(notice, connector_version(SOURCE)):
                    raise AssertionError("Fresh official STAN notice not inserted")
            stored = store.read(SOURCE, limit=2)
            if len(stored) != len(notices):
                raise AssertionError("Official STAN metadata missing from SQLite")
            for notice in notices:
                record = next((n for n in stored if n.identity == notice.identity), None)
                if (record is None or record.customer != notice.customer
                        or record.deadline != notice.deadline
                        or record.initial_price != notice.initial_price
                        or record.currency != notice.currency):
                    raise AssertionError("STAN independently verified original fields changed in storage")
                if not record.customer or not record.deadline:
                    raise AssertionError("STAN fields missing after SQL persistence")
                buyer_words = [word for word in record.customer.split() if len(word) >= 5]
                if not buyer_words:
                    raise AssertionError("Original STAN buyer has no usable keyword")
                queried = store.read(SOURCE, limit=5, search_terms=(buyer_words[0],))
                if not any(n.identity == record.identity for n in queried):
                    raise AssertionError("First-party STAN buyer not searchable")
                if store.upsert(notice, connector_version(SOURCE)):
                    raise AssertionError("STAN idempotent SQL identity duplicated")
        finally:
            db.close()
    return {
        "original_distinct_notices": len(notices),
        "buyer_verified": buyers,
        "deadline_verified": deadlines,
        "explicit_rub_prices": sum(n.currency == "RUB" for n in notices),
        "sqlite_persisted_and_searchable": len(notices),
        "production_changed": False,
    }


def main():
    try:
        evidence = verify()
    except Exception as error:
        print("RU_STAN_METADATA_LIVE=BLOCKED_" + type(error).__name__)
        # Fail closed, but never print source HTML, title, customer, URL or
        # raw transport data into public CI logs.
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_STAN_METADATA_LIVE_EVIDENCE=" + json.dumps(evidence, sort_keys=True))
    print("RU_STAN_METADATA_LIVE=PASS")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
