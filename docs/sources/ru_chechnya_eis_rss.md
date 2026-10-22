# Чеченская Республика — региональный ЕИС 44-ФЗ (VALYQON)

Status: **draft; production disabled; no verified live delivery** until all checks described below pass. No national search result is counted as a Chechnya tender merely because the title mentions the region.

## Original source and scope

- Original publication: [ЕИС](https://zakupki.gov.ru/). Official regional authority: [Комитет Правительства Чеченской Республики по госзаказу](https://gostorgi-chr.ru/). The committee homepage is not claimed to expose a live tender API.
- Supports **44-ФЗ** RSS results only. This does not claim to cover 223-ФЗ, commercial platforms, regional small purchases outside ЕИС, or all federal buyers delivering to Chechnya.
- Each accepted entry must carry a valid EIS 44-ФЗ original registry number and an official original URL, with Chechnya/Grozny evidence in the EIS customer/region fields.
- One original 44-ФЗ procedure is deduplicated across `eis` and `ru_chechnya_eis`.

## Configure, only after successful acceptance

1. Open EIS **advanced procurement search** using the browser on a trusted host. Select 44-ФЗ and the customer location **Чеченская Республика**. Click its official RSS link; copy the exact full RSS URL, preserving the search parameters. **Do not invent `customerPlace` or region IDs**. An optional explicit text search for Чеченская Республика is narrower than the regional filter.
2. Set `RU_CHECHNYA_EIS_RSS_URLS` to that URL and `RU_CHECHNYA_EIS_ENABLED=true`. It is required to supply both settings; empty URLs while enabled cause an error. If using PowerShell, set environment variables for the current process with `$env:RU_CHECHNYA_EIS_ENABLED="true"` and `$env:RU_CHECHNYA_EIS_RSS_URLS="<copy official link>"`.
3. Keep `EIS_DIRECT_ENABLED=true` with a **verified** trusted CA source. On Windows use `EIS_SYSTEM_TRUST_ENABLED=true` when official server-auth trust has been separately checked. On Linux/WSL use a vetted `EIS_CA_BUNDLE_FILE` if necessary. **Never use verify=false, skip TLS checks, or download and trust a server-supplied chain.**
4. In an isolated environment run `python -B -m pytest -q tests/test_ru_chechnya_eis_rss.py` then `python -B -m scripts.ci_ru_chechnya_eis_real_worker`. A successful unit suite is **not** equivalent to live source validation.
5. Alternatively dispatch the branch's `RU Chechnya EIS 44 regional source gated acceptance` workflow with the exact RSS URL. The live job requires a pre-authorized self-hosted Linux runner with verified EIS trust path supplied via the `VALYQON_RU_EIS_CA_BUNDLE_FILE` GitHub Actions repository variable. No live EIS or Telegram credentials are present in the PR CI.

## Merge gate — all of the following

- PR tests and all required repository checks green on the current head commit.
- Real official EIS RSS and original notice links with strict HTTPS and 44-ФЗ verification; **nonzero real notices** from the Chechen Republic.
- Real leased `connector.sync.v1` Worker has persisted notices to disposable SQLite with no skipped entries, user exact-number and title-keyword searches recover the same notice, unrelated queries return nothing.
- Repeat delivery is idempotent. A real regional tender reaches the **local Telegram message boundary** in the strict script; the script **does not send Telegram externally**.
- Separate operator evidence of **real Telegram API acknowledgement to an authorized test chat**, plus deployment monitoring, is required before claiming *actual delivery to users*. Never report local capture as external delivery.
- Approve and merge only after those proofs. Turn on production configuration only in a separate explicitly reviewed operator activation.

## Failure handling

No live feed, empty/ambiguous regional data, redirect, invalid CA, challenge, HTTP error, wrong law, or invalid original ID => **BLOCKED**, no merge and no production activation. The acceptance script prints `RU_CHECHNYA_EIS_STRICT_LIVE=BLOCKED_...` with a nonzero exit code. The offline PR workflow is never a substitute for live verification.

## Related files

- `app/sources/ru_chechnya_eis_rss.py`: strict regional adapter
- `app/sources/catalog.py`, `app/monitoring/config.py`: source registration and operator opt-in
- `app/sources/ingestion.py`: official host and bounded Worker requests
- `app/sources/ru_notice_identity.py`, `app/sources/ru_dedup.py`: original EIS duplicate handling
- `scripts/ci_ru_chechnya_eis_real_worker.py`: strict real data → Worker → SQL → search → local alert acceptance
