# Ankara EGO official public transit e-tenders

Issuer: **EGO General Directorate (Ankara city public transit)**, government
tender listing `https://www.ego.gov.tr/ihaleler`. This is **not** the national
EKAP search and not ASKİ or Ankara city hall procurement, which are separate
buyers. Public examples include metro railcar parts and workshop equipment
with official KİK tender numbers and bidding dates after 17 October 2026.

The `tr_ego_transport` connector performs at most one GET of the published
EGO **İHALE İLANLARI** current-bid listing and four permitted, same-host
individual public detail GETs. Strictly requires e-ihale notices, normalized
KİK number, official same-host detail URL
`https://www.ego.gov.tr/tr/ihale/detay/{numeric-id}/{slug}?tip=0`,
matching original title and government buying agency and future bid date.
Excludes "ihale sonuçları" (awards), expired bids, publications with missing
source detail, unverified links and guessed budgets. Some tenders permit
only suppliers with the required local registration; discoverability never
implies automatic eligibility.

This operator-only source defaults OFF and is registered only when
`VALYQON_ASIA_TURKEY_EGO_ENABLED=1`. On an explicitly configured trusted
production host with the shared persistent DB, running supervised
`python -m app.jobs.worker --connectors`, and existing scheduler, set
`VALYQON_ASIA_OPERATIONS_ENABLED=1`, then enqueue/search with:

```sh
python -m app.sources.asia_all --enqueue --source tr_ego_transport
python -m app.sources.asia_all --search "metro" --source tr_ego_transport
```

Actual provider→real Worker→temp SQLite→stored notice matching and
dedup must pass independently under GitHub hosted CI before main merge.
Neither production AWS deployment nor customer notification delivery
is automatically performed by GitHub merge.
