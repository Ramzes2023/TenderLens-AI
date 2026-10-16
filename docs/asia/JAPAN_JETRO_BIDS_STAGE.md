# Asia expansion — Japan JETRO competitive bid RSS (staged only)

Date: 16 October 2026. Branch: `feat/asia-jp-jetro-bid-rss-20261016`. PR: [#61](https://github.com/Ramzes2023/TenderLens-AI/pull/61).

## Distinguish the three unrelated Japanese channels

- **New candidate `jp_jetro_bid`**: `https://www.jetro.go.jp/rss/proc_bid.xml`. This is JETRO's **own competitive-bid announcements** in Japanese, *not all Government of Japan tenders*.
- **Existing `jp_jetro_national` and `jp_jetro_local`**: the separate English-language Japan-wide JETRO procurement search database. These remained research-only because the trusted Asia runner previously observed HTTP 503. They are not activated by this PR.
- **Existing six Hong Kong sources**: unchanged, still controlled by `VALYQON_ASIA_SOURCES_ENABLED=1`. The Japan candidate has its **own** `VALYQON_ASIA_JETRO_BID_ENABLED=1` and is excluded from `asia_enqueue`.

## Fail-closed network and data boundaries

The new JETRO adapter performs one anonymous official HTTPS request on `www.jetro.go.jp` with no redirects, bounded response size and SSRF/public-IP protection inherited from the established `source_client`. It accepts only RSS 1.0, RSS 2.0 or Atom item links to individual `/procurement/bid/<unit>/<hex-id>.html` detail pages, rejects unrelated links, award/result/cancellation titles, suspicious XML declarations and empty upstream responses. Stable identity is the SHA-256 of the verified canonical detail URL. Missing date, bid deadline, price and award status **are not invented**.

The official procurement listing [JETRO bidding notices](https://www.jetro.go.jp/procurement/bidtop?media=pc) and independent RSS discovery support the candidate URL's purpose, **not successful live ingestion from a GitHub runner**.

## Mandatory acceptance before merge

1. `jp-jetro-bid-offline-contracts` must pass unit/security and existing source/worker regression tests.
2. `jp-jetro-bid-real-worker-sqlite` must retrieve a real official item, enqueue `connector.sync.v1`, execute `Worker.run_once()`, persist a valid `TenderNotice` in disposable SQLite, return that same identity through keyword snapshot search, and reject a duplicate queue insertion.
3. The current PR HEAD must have green general Linux/Windows CI, Russian source contracts, original six-source Asia acceptance, and relevant other cross-team checks.
4. Any failure, empty JETRO RSS, blocked network, changed feed URL structure or incompatible parser leaves the PR as **Draft**. Never bypass failing live evidence with synthetic fixtures.
5. Production deployment, actual operator activation, automatic scheduling, AWS egress and customer-authenticated search require separate review.

**Status:** implementation staged in an isolated PR. No unverified claim of a seventh live-working Asian source. No production or user data changed.
