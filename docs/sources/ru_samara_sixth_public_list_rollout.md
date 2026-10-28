# Samara sixth public source: verified LIST ONLY, opt-in, no details

## What is and is not proven
The official public native JSON endpoint at
`https://webtorgi.samregion.ru/smallpurchases/GzwSP/NoticesJson`
provides real first-party procurement *listing* rows with external ID,
municipal notice number, title, public buyer, published amount (when
available) and public submission deadline. They can be safely indexed
only if their native row identity and deadline are verified again on
each real feed run.

**Individual procurement detail pages are NOT independently verified**.
The official list-supplied direct detail returned HTTP non-2xx and the
publisher did not announce a usable anonymous alternate. Never pass a
third-party tender index as official, invent detail documents, links,
authorised access, or claim full document coverage. The stored notice
intentionally points at the official public GRID, not a fabricated
individual detail page. Public guest previews contain ONLY actual
title/price/currency/deadline; existing limited previews keep details
locked. The user must independently confirm terms and access on the
official platform to bid.

## Deadline semantics
The real native JSON table publishes `collecting_endDate` as either
`DD.MM.YYYY`, `DD.MM.YYYY HH:MM[:SS]`, or a normalized local wall-clock
ISO string with seconds. Source does not independently attest the zone.
The active guest API accepts only a date safely beyond the entire
global UTC+14 local day, or a local submission clock strictly after the
global UTC+14 wall clock, **without guessing Moscow or UTC**. Unknown,
expired, contradictory, malformed or stale rows are excluded.

## Exact release gates
1. A **real** fresh official GRID GET → anonymous on-page form token
   → publisher `NoticesJson` POST → independently validated native
   numbers, buyer and title.
2. A genuine leased/fenced Worker → **ephemeral** SQLite →
   keyword and native row lookup. At least one real source-owned row
   must have a safely future submission deadline, observed within 2 h.
3. Strict guest projection rejects wrong host, invented deep links,
   malformed ID, missing buyer, altered region, source-price/currency
   mismatch and all private details. No duplicate native IDs.
4. The actual isolated SQLite candidate verifier
   `python -m scripts.verify_samara_list_sixth_candidate` must return
   `CANDIDATE_ONLY` based on current stored rows. It is not independent
   publisher proof.
5. Exact-head GitHub CI (including Linux/Windows/Docker, source-specific
   LIVE and the existing public-source regression suite) all green.
6. **Operator-only VPS**: new release directory, online source-volume
   SQLite backup and restore trial, verify previous image and rollback,
   combine in this exact order:
   `compose.yaml`, `compose.south-ural.yaml`,
   `compose.kavkaz-rf.yaml`, `compose.lenobl.yaml`,
   `compose.samara-list.yaml`.
   Test genuine Worker receipts and at least one future source-owned row
   before switching isolated guest-sources. Never recreate main API,
   Caddy, credentials, payments, or production SQLite.
7. Real external guest **HTTPS** title/deadline match, previous five
   sources and GigaChat preserved, expired hidden, Caddy/production hashes
   identical, all six hourly jobs enqueue/run successfully. On any
   regression rollback, and report `STAGED_ONLY` or `ROLLED_BACK`.

This feature is a **sixth source of authentic public listing notices**,
NOT six independent publication platforms, authenticated detail access,
or a complete view of all Samara tenders. The EIS and Fabrikant reposts
can overlap economically; cross-platform dedup still needs separate
evidence. Production stays at five sources unless all release checks pass.
