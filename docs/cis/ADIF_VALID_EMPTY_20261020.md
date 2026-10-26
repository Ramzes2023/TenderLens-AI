# ADIF valid-empty versus genuine active intake — 20 October 2026

**Root cause:** current first-party ADIF procurement announcements close for
bids on 19 October 2026. At 20 October the strict production source returns
no *open* offers, correctly. The previous acceptance script nevertheless
required at least THREE active records, and the combined MD/AZ script required
an ADIF row in SQLite. The result was two misleading red live workflows on
otherwise valid dated source content. Source research: https://adif.gov.az/az/sale/

This patch DOES NOT relax the source parser, reuse expired notices, change
network policy, edit tenant data, open production, or fake data. Both scripts
run the same real official HTTPS → fenced Worker → temporary SQLite. The
worker job MUST finish successfully, with zero fetched, accepted, stored,
updated or skipped rows before ADIF may report VERIFIED_EMPTY. Empty-result
search is required to return no hits. Missing documents, invalid schema,
unsafe network responses, errors, retries exhausted, or lost leases remain
RED. If at least one active bid exists, it must be genuinely stored and
retrievable via keyword search and original first-party URL, as before.

The three-source acceptance ALWAYS requires real positive MD e-Licitatie
and AZ Azeristilik records with genuine buyer query and provenance. ADIF
may be VERIFIED_EMPTY and is clearly printed with
`active_tender_delivery_verified=false`. Never claim three live *positive*
feeds or actual Telegram delivery from a valid-empty status.

Offline regression checks deliberately test the positive/empty split and
all count/source mismatches; ONLY the real hosted runner proves current live
ADIF state. Both workflow gates remain mandatory, non-skippable, and red if
live network/source/parser or other positive feeds fail. No PR is safe to
merge unless every exact-HEAD CI workflow passes.
