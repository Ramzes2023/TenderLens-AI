# Ingushetia live integration correction — 2026-10-19

This report supersedes the earlier *local discovery blocked* finding, not the
production or real Telegram acceptance gates. Base PR #222 SHA:
`b5414553d2630b4145b9336a0dde7c5ae8a9bf13`.

## Root causes and corrections

1. Hosted EIS runs failed at connection establishment (`ConnectTimeout` or
   `ConnectError`), before an HTTP response. These observations do not establish
   a certificate or RSS parsing error. All four registered domestic/international
   self-hosted runners were offline at this audit. No runner or server was started.
2. Local live EIS `fz44=on&regions=06&pageNumber=1` returned HTTP 200 with
   **national** notices. Its RSS description's selected buyer-region value was
   empty. The adapter correctly excluded those rows. The default now uses the
   existing official `searchString=Ингушетия&morphology=on&pageNumber=1&fz44=on`
   RSS shape, independently fetched successfully on this run. Every accepted
   result still needs publisher-owned buyer/region evidence. This is conservative
   text-based regional discovery, not proven exhaustive republic-wide coverage.
3. Actual Fabrikant table HTML puts the procurement-name anchor and unrelated
   badges (`СМП/СОНО`, `1875`) in the same title cell. The parser previously
   concatenated them, so real detail-title verification failed. The adapter now
   reads the title from the procurement link in the name cell and requires an
   exact match with the card's labeled procurement-name field.
4. The organizer is not necessarily the customer. Cards identify the committee
   as the organizer but name hospitals/other buyers separately. The adapter now
   extracts actual visible customer headings. Region proof still requires the
   committee name and exact INN `0608058533` in the organizer section.
5. Acceptance previously supplied rows directly through a monitor subclass.
   Live acceptance now dispatches through the actual Worker SQL snapshot catalog.
   SQL replay changes `last_seen` and can reorder rows; notification verification
   now matches original numbers rather than assuming list order.
6. PR #222 added two optional adapters without updating the public directory's
   old count expectations. Both general-CI failures were stale inventory
   contracts. Tests now assert the precise intended optional-key set and cover
   registering either Ingushetia adapter without duplication.

No TLS verification, host/DNS protections, authorization, tests or source opt-ins
were disabled. No production databases or subscriptions were opened.

## Actual discovered and verified notices

Live `https://44.fabrikant.ru/44/catalog/procedure?q=0608058533` returned ten
regional committee links, independently of the four previously seeded examples.
The adapter fetched and verified these three cards and the Worker fetched them
again from the current listing:

| EIS original number | Publication | Procurement | Actual customer |
| --- | --- | --- | --- |
| 0114500000826002390 | 19.10.2026 17:01 | Поставка ГСМ (Бензин АИ-95) | Республиканский кардиологический диспансер |
| 0114500000826002391 | 19.10.2026 15:18 | Капитальный ремонт медицинского мобилизационного центра «Резерв» | Медицинский мобилизационный центр «Резерв» |
| 0114500000826002364 | 16.10.2026 17:01 | Поставка лекарственных средств | Республиканский клинический центр психиатрии и наркологии |

Card URLs are included in the accompanying JSON evidence. All three publication
dates were checked to be within 30 days of the live run. No fixed notice numbers,
cached HTML, browser search results or fixtures feed the live acceptance.

The corrected EIS RSS separately discovered `0114100000126000011`,
`0114100000126000012`, `0114500000826002384`, `0114500000826002383`,
`0114500000826002382`. EIS original HTML-card verification remains blocked in
this environment; RSS availability alone is not full EIS-route acceptance.

## Verified chain and limits

- Leased/fenced Worker: `succeeded`; the same three verified EIS numbers survived
  the Worker, disposable SQLite and query stages.
- SQL searches: exact number, actual procurement title and user terms `Бензин`,
  `работ`, `лекарственных` all found the corresponding originals.
- Production profile filtering: matching profile accepted; excluded keyword and
  incompatible region rejected each corresponding notice.
- Replay upsert inserted zero additional rows. Notification seen-state rejected
  the same originals when represented by the generic EIS adapter. Source-local
  storage identities remain separate, while original notification identity is
  `("eis_44", notice_number)`.
- Three messages were formatted and acknowledged by an **isolated in-process
  receiver** through the actual monitor loop and SQL snapshot catalog.
- **Real Telegram API ACKs: zero; not tested.** No dedicated authorized test
  bot/chat configuration was supplied at the time of this report.
- Targeted adapter, ingestion, lease/fence, SQL snapshot, monitoring and identity
  regressions: **216 passed, zero failed**; public source-directory regressions:
  **7 passed, zero failed** (223 total), one upstream Starlette deprecation
  warning. Initial use of an incomplete shared Python environment failed import
  collection (`aiogram` missing); the final checks used this clone's own `.venv`
  with `requirements-dev.txt` installed.

The additional complete Windows suite initially produced **3589 passed,
9 failed, 3 error events, 7 skipped, 1 xfailed**, plus 518 passed subtests.
Seven failures were the missing measurement-output directory in the Windows
analytics test itself; two were Git `core.autocrlf=true` changing pinned fixture
bytes; the oversized certificate parameter also exceeded Windows' 32767-character
environment-variable limit through pytest's generated ID. Tests now create their
own output directory, `.gitattributes` preserves the exact committed bytes of
the two affected evidence fixtures, and the same certificate payloads have short
explicit test IDs. No pin, certificate assertion or input was replaced.

One Windows handle-count teardown error reported a **decrease** from 416 to 409
handles in the combined suite; its exact equality assertion is unchanged.
Rechecking all five affected modules after preparation yielded **106 passed,
zero failed/errors**. Their two warnings concern Starlette deprecation and the
pre-existing absence of original raw TED captures; neither is live Ingushetia
evidence. The general CI workflow now also runs on correction PRs targeting the
Ingushetia feature branch, rather than waiting until an eventual PR to main.

The public source is the accredited Fabrikant mirror of EIS 44-FZ. It is **not**
an additional independent original publisher. Its query covers purchases routed
through the specified committee, not a demonstrated exhaustive list of every
Ingushetia buyer. A separate republic-wide native publisher and a universal 2026
regional small-purchase platform remain **unverified**, not proven absent.

## Reproduction in an authorized environment

```powershell
python -B -m scripts.ci_ru_ingushetia_fabrikant_worker --evidence-dir artifacts/new-isolated-proof
python -B -m scripts.ci_ru_ingushetia_live_worker
```

The optional real Telegram test must receive an explicitly supplied, separate
dotenv file containing `INGUSHETIA_TEST_TELEGRAM_BOT_TOKEN` and
`INGUSHETIA_TEST_TELEGRAM_CHAT_ID`. Never put secrets in Git, command arguments,
CI output or chat. Ordinary production `TELEGRAM_BOT_TOKEN` is not used.

```powershell
python -B -m scripts.ci_ru_ingushetia_fabrikant_worker --telegram-test-env C:/private/ingushetia-test.env --evidence-dir artifacts/new-telegram-proof
```

This command performs fresh discovery, original-card checks, Worker/SQL/search
and profile verification before sending to the dedicated test destination. It
accepts delivery only when Telegram returns the exact chat, text and positive
`message_id` for every verified notice; only then does the monitor persist seen
state. Empty/missing test configuration fails without constructing a bot or
creating a subscription. The SQL/evidence directory must be new, preventing an
accidental overwrite of another run.

## GitHub and release gates

PR #222 at the audited SHA had **83 successful, 6 failed and 1 skipped checks**.
Failures included Ingushetia live acceptance, general tests, two B2B jobs and two
Asian-source jobs. The general tests' two stale optional-adapter expectations
are corrected here. B2B and Asian-source failures are not repaired or hidden by
this change. Correction checks must be examined on the correction PR's exact SHA.

Both Ingushetia adapters remain default-off. PR #222 must remain Draft and
unmerged until all mandatory checks and the real authorized Telegram delivery
test pass. No deployment, production enablement, merge or customer messaging
has occurred. Work is isolated in the second Codex's own clone and correction
branch; the first Codex's worktrees and processes were not modified.
