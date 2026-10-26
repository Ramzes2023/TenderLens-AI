# PR #226 continuation from 6006c4b

Scope: current codex/ingushetia-fix-20261019-193617 checkout only. No other
Codex folder/process, WSL, VALYQON-RU-01, production or subscription touched.
No runner provisioned/started, no Telegram request, no merge, no disabled gate.

## Reviewed CI, not inferred from diagnostic job color

For head 6006c4bebc9c7887311aeca744b2c7a697c6a996:
- Source contracts: PASS, run 39309527470.
- Strict Ingushetia contracts: PASS, run 39309527269.
- Live Worker gate: FAIL, job 118255202187 in run 39309527269.
  EIS: ConnectError -> OSError, no certificate verification code.
  Fabrikant: ReadError -> BrokenResourceError -> OSError. This is a transport
  read failure; nested IndexError/SSLWantReadError do not establish a parser bug.
- Route diagnostics: run 39309527558, Linux job 118255203896, Windows
  job 118255203668. Both pinned-root probes load strict CA/hostname checking,
  then ConnectTimeout with no HTTP response/certificate-specific error.
  Other soap4 detail routes return 200 while soap4 listings return 404;
  they cannot replace working discovery on the adapter host.

Exact selected job evidence is retained in pr226-ci-job-*.txt. GitHub links:
https://github.com/Ramzes2023/TenderLens-AI/actions/runs/39309527269
https://github.com/Ramzes2023/TenderLens-AI/actions/runs/39309527558

No evidence here identifies geoblocking, absent CA, or adapter parsing as the
cause of hosted failures. Code correction: classify httpx.ReadError as
response_read_failure instead of unclassified, retaining redaction and retry
semantics. No increased timeout, TLS bypass or fixture fallback.

## Safe alternative environments

1. This existing Windows checkout is the currently proven accessible environment.
   Run bounded source-only checks with strict scoped CA and disposable test SQL.
   It supplies independent evidence, never a replacement green hosted check.
2. A fresh standalone Linux VM on a separately authorized network can run the
   reviewed immutable checkout directly, WITHOUT registering any Actions runner.
   First test the exact RSS/list/card URLs, then the full Worker acceptance.
   No shared host mounts, private routes, production secrets, metadata access,
   inbound service, or persistent bot. Destroy guest and disk after bounded run.
   No VM/account/network/cost permission was provided; none was provisioned.
3. GitHub larger runners offer controlled/static egress and Azure private
   networking options, subject to account support/configuration/cost. This is
   only a candidate: no evidence their network reaches EIS/Fabrikant. Keep an
   isolated network without production peering; do not claim guaranteed access.
4. Ephemeral self-hosted VM is a last option, subject to explicit permission
   and the existing isolated-runner review. A standalone VM avoids listening
   for queued Actions jobs. RU-01 remains excluded by user instruction.

Official references checked 2026-10-19:
https://docs.github.com/en/actions/reference/runners/github-hosted-runners
https://docs.github.com/en/actions/how-tos/manage-runners/larger-runners/manage-larger-runners
https://docs.github.com/en/organizations/managing-organization-settings/about-azure-private-networking-for-github-hosted-runners-in-your-organization

## Actual repeated live acquisition, not a fixture sequence

Command: .venv/Scripts/python.exe -B -m scripts.ru_ingushetia_poll_audit
--polls 2 --interval-seconds 60. Exit 0.
Poll starts UTC: 2026-10-19T19:24:30.192969+00:00 and
2026-10-19T19:25:35.798050+00:00. Both sources PASS in both polls.
EIS (including separate original checks for its first two cards):
0114100000126000011, 0114100000126000012, 0114500000826002382,
0114500000826002383, 0114500000826002384.
Fabrikant (each independent same-host detail verified):
0114500000826002364, 0114500000826002375, 0114500000826002376,
0114500000826002390, 0114500000826002391.
The second poll contains exactly the same original IDs. Newly observed: ZERO.
2375/2376 are additional baseline rows from a five-card fetch, NOT new
publications compared with the earlier three-card acceptance.

The new bounded audit retains cumulative original keys across its polls,
including crossfeed duplicates, changed titles, temporary disappearance and
failed polls. First success per source is baseline only. History is confined
to one audit invocation; it is not a production discovery service. The durable
production dedup path is separately covered by the real Worker/SQL/monitor test.
First observed identity does not prove a new upstream publication timestamp.

Continuous readiness remains LIMITED: sources are opt-in/default OFF; no
deployment/scheduler activated. Bot monitor can poll the enabled live RU
catalog on its configured interval with existing durable delivery dedup.
The separate Worker enqueue path is hourly idempotent and operator-triggered;
the approved RU batch CLI currently excludes these gated Ingushetia sources.
Fabrikant caps at five cards, EIS accepts a bounded RSS window and conservative
buyer/region corroboration; pagination/backfill/full republic coverage are not
proven. A burst beyond those windows can be missed. Do not advertise complete
continuous coverage before a reviewed cadence/backfill policy and deployment
network acceptance are established. No newly published ID was observed here.

## Separate opt-in Telegram Bot API check: PREPARED, NOT EXECUTED

Module: scripts.ru_ingushetia_telegram_test. No dotenv/application config,
production DB, customer subscriptions, scheduler, polling bot or credential
fallback. Default invocation prints NOT_REQUESTED, NETWORK_REQUESTS=0.
It sends one visibly synthetic diagnostic, not a procurement or acquisition
proof. This intentionally isolates actual Bot API transport from live sourcing.

Only after explicit operator permission and an authorized dedicated test bot/chat:
- Provide TEST_TELEGRAM_BOT_TOKEN through a secure local environment/secret
  channel, never commit it or put it in a CLI argument. Do not reuse production.
- TEST_TELEGRAM_BOT_ID: independently confirmed dedicated bot numeric ID.
- TEST_TELEGRAM_CHAT_ID: authorized numeric private/test group ID, no usernames.
- TEST_TELEGRAM_SEND_AUTHORIZED=YES_TEST_CHAT_ONLY.
- Recipient must /start the bot or add it to the isolated group first.
- Run python -B -m scripts.ru_ingushetia_telegram_test --send
  --confirm-test-chat <same numeric TEST_TELEGRAM_CHAT_ID>.

getMe/getChat identities are checked before sendMessage; channels rejected.
HTTPS verification enabled, redirects and environment proxies disabled.
No automatic retries: after send_attempted, failure may mean delivery occurred;
inspect the test chat before any explicit repeat. Output hides token/chat/API
descriptions; successful evidence contains matching bot/chat booleans,
message_id and unique marker. Recipient confirmation remains PENDING until
the authorized tester confirms appearance. API acknowledgement is not reading.
No automatic workflow consumes TEST_* secrets in PR events.

Official contract: https://core.telegram.org/bots/api#sendmessage

## Verification

- Focused contracts including new Telegram/poll tests: 93 passed before the
  additional Worker sequence test.
- New tests plus jobs/Worker/monitor regressions: 159 passed, one existing
  Starlette/httpx deprecation warning. Includes three actual leased Worker
  cycles on synthetic notices: insert A; update A + insert B; reappear A.
  Only B is unseen after the first simulated acknowledgement; an EIS mirror
  of A creates no new alert. No network send is used in these offline tests.
- The previously reported 321 tests are preserved as prior evidence, not
  presented as newly rerun. Required live CI remains fail closed.

Remaining gates: hosted full live acceptance; authorized test bot/chat and
explicit send permission; actual API acknowledgement + recipient confirmation;
observing genuinely new publication IDs and proving continuous coverage/cadence.

## Resumed-session verification (2026-10-19)

- Reviewed staged diff, poll audit and test-only Telegram guard. No real Telegram request.
- Fresh focused + jobs/Worker/monitoring run: 235 passed, one existing Starlette/httpx deprecation warning.
- Initial run: 86 passed, 8 setup errors caused solely by inaccessible default pytest temp root. Rerun used a fresh unique workspace basetemp; no test assertions changed.
- Repeated full live Worker acceptance locally: PASS via official_eis_rss; original cards 0114100000126000011 and 0114100000126000012 verified; leased Worker succeeded; 10 SQL rows searchable; 2 isolated sink dispatches; replay duplicates 0. FAILURE_ROUTE_SUMMARY=[].
- Local live success does not resolve GitHub-hosted network failure. No production, existing runner, other Codex workspace, or merge actions.
