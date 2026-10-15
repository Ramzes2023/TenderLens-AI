# VALYQON AI — Asian public procurement six-source staging

**15 October 2026. Review only. Do not merge or enable in production.**

## Scope

Branch: `feat/asia-public-procurement-six-20261015`
PR: [#36](https://github.com/Ramzes2023/TenderLens-AI/pull/36)

| Key | Country | Official upstream | Initial GitHub live observation |
| --- | --- | --- | --- |
| `hk_ha_works` | HK | Housing Authority tender RSS | BLOCKED |
| `hk_ha_leasing` | HK | Housing Authority commercial tender RSS | BLOCKED |
| `hk_emsd_tenders` | HK | EMSD tender RSS | BLOCKED |
| `hk_emsd_consultancy` | HK | EMSD consultancy invitation RSS | **FETCH_SQLITE_SEARCH_VERIFIED** (1 item) |
| `jp_jetro_national` | JP | JETRO national listing | BLOCKED |
| `jp_jetro_local` | JP | JETRO local listing | BLOCKED |

The first GitHub-runner job on `8846c023d6e397fcab1a7f464aaa60d5d12ca228` finished with
**1 of 6** sources having at least one actual notice, validated and saved to an isolated SQLite
database and retrieved through the source snapshot search. This is **NOT** six-source live
acceptance, proof of ongoing fresh tenders, complete detail-page verification, AWS
reachability, authenticated AI search, or production readiness.

The later diagnostic commit `fae8b2a82ae7091c22b470e76e61119f0921f6d3`
made transport/parse failures distinguishable, but GitHub Actions runs created for
that commit failed *without any job steps or runner allocation*; a second attempt
of the Asian job had the same runnerless outcome. Do not interpret these as an
adapter regression or a successful live check. The external CI infrastructure
must work before repeat evidence is available.

## Architecture and safeguards

- Integrated into `SourceCatalog` and `MultiSourceFetcher`; normalized
  `TenderNotice` can be stored in `OpportunityRepository` and searched through
  `snapshot_catalog`.
- Six server-owned host entries in `app/sources/ingestion.py::HOSTS`
  permit standard connector-worker routing; existing per-source bounded HTTPS
  transport and public-IP/SSRF enforcement remain in place.
- `VALYQON_ASIA_SOURCES_ENABLED` defaults to **off**. Setting it to
  exactly `1` stages the registrations, but is not a release approval.
- 1 MiB max per listing, fixed upstream official HTTPS URLs, no third-party
  redirects, no login, passwords, custom CA, CAPTCHA bypass or dynamic targets.
- A source without demonstrable linked tenders raises `SourceError` instead
  of returning an empty successful result.

## Release acceptance (ALL required)

1. Re-run `Asian public procurement acceptance` on the latest head. Both
   `asia-six-offline-contracts` and `asia-six-real-live-sqlite` must pass;
   the live step must print `ASIA_SIX_SOURCE_FETCH_SQLITE_QUERY_VERIFIED=6/6`.
2. Verify all branch `CI`, Russian source contracts and any relevant full
   PostgreSQL acceptance jobs are green on the **same current PR HEAD**.
3. Confirm the data represents genuine tender notices (not awards / news /
   merely 200 HTML pages). Check individual detail URL, title, source identity
   and deadlines where actually supplied. Do not manufacture missing fields.
4. Execute the worker and database replay tests on an isolated test instance
   with concurrent lease fencing and crash/retry guarantees.
5. Obtain evidence of accepted use/rate limiting and reachability from the
   eventual AWS production environment. Retain source health alerts.
6. Review changed files for regressions and approve activation/merge separately.

**Until then: leave PR #36 draft, sources off, production and `main` unchanged.**


## 15 October continuation — genuine JETRO URL correction

A public Japanese government procurement detail confirms that **local** JETRO
notices are addressed as `/en/database/procurement/local/articles/<16-character
hex ID>.html`, rather than the old, incorrect national-style
`/local/articles/<numeric>/<numeric>.html` URL. For example, the official
JETRO regional detail is:
`https://www.jetro.go.jp/en/database/procurement/local/articles/b25795fdff1a1aba.html`.
National notices still use the separate numerical hierarchy, e.g.
`https://www.jetro.go.jp/en/database/procurement/national/articles/379164/2026012100070000.html`.

The branch now validates both forms separately, retains stable distinct
`external_id` values and tests wrong-section/cross-host links. The
pre-existing local parser necessarily discarded legitimate local links.
This correction is **offline contract evidence only**, not proof of successful
new live ingestion from JETRO.

The fallback search form is limited to a fixed official HTTPS host, bounded
two requests in the connector worker, and JETRO's *before deadline*
filter. The fallback must still parse real competitive procurement rows,
not generic search-page text. The two expected URLs need live-host
confirmation and repeatable database/search proof before approval.

The other Hong Kong RSS feeds are officially documented by Hong Kong
Housing Authority and EMSD, but may be empty or blocked by a particular
network origin; status remains unknown until real transport and persisted
notices are proven. Fail-closed logic must not fabricate tenders.

**CI blocker remains external to Python execution:** GitHub-hosted Actions
report `runner_id=0` and `steps=[]` immediately for Asian, Russian and
general CI jobs. A local self-hosted PR run is **not** an acceptable
workaround for executing unreviewed pull request code. GitHub Actions
account settings or a trusted manual execution pathway must be resolved
before any claim of green acceptance.

**Main/production unchanged; PR #36 remains draft and unmerged.**


## Operator-only ingestion path (added after pipeline review)

The shared worker queue intentionally has **no automatic per-source scheduler**:
`python -m app.sources.enqueue --source <key>` enqueues one explicitly
configured source. Six independently configured adapters in the registry do
**not** imply that scheduled background downloads, saved-notice searches, or
notifications have been enabled. Do not describe registry registration alone
as production delivery.

To reduce manual error, the PR adds `app/sources/asia_enqueue.py`, which
validates all six routes and can queue a same-hour idempotent batch through the
existing `ConnectorSyncService`. The dry run is safe:

```sh
python -m app.sources.asia_enqueue
```

Only **after** six-source live checks, full current-head CI, isolated real
database and worker/lease checks, network/rate-limit review, and operator
approval, the execution path would be:

```sh
VALYQON_ASIA_SOURCES_ENABLED=1 python -m app.sources.asia_enqueue --enqueue
```

This is an explicit operator command, not a new daemon, no AWS change, and
not an action to run during an unreviewed pull request. The existing worker
must be running and configured to accept `connector.sync.v1`; a separate,
approved operator scheduler is required for recurring hourly delivery.
All requests use the established host allowlist and bounded transport.
Local keyword queries operate on persisted opportunity snapshots; dry-run
and registration alone create **zero searchable tenders**.

## Current external CI blocker

The repository's screenshot of the failed GitHub-hosted job gives the
specific GitHub annotation: *The job was not started because recent account
payments have failed or your spending limit needs to be increased.*
Therefore rerunning unmodified hosted jobs cannot produce green CI before
the account owner resolves GitHub Actions billing/spending limits. The
`VALYQON-RU-01` self-hosted runner must not execute unreviewed PR code.
We must not bypass this release gate or pretend a fixture-only test verifies
the live supply.
