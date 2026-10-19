# PR #226: original-card investigation and repeat, 2026-10-19

Work is confined to codex/ingushetia-fix-20261019-193617 in the second checkout.
No production database, subscriptions, other checkout, WSL distribution or
self-hosted runner was changed or started. Docker is unavailable; its service
was not started.

## EIS originals

Fresh RSS and the official number-filtered EIS search both publish the same
URL for 0114100000126000011:
https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=0114100000126000011
The official search additionally publishes printForm/view.html, listModal.html
and ea20/view/documents.html. No procedure-type substitution or invented route
was introduced. Both the original and published print form returned HTTP 200
with matching number and verified TLS. See the bounded extracted public links
in ingushetia-eis-official-links-current-20261019.json.

An initial RSS request in this repeat returned 404; a later request returned
200. The original-card checker now uses the same declared User-Agent as the
RSS client. IMPORTANT: a subsequent alternating User-Agent experiment returned
200 for BOTH python-httpx and TenderLens identities (four requests). Therefore
User-Agent causation is NOT established, and the historic 404 must be treated
as intermittent upstream behavior, not proof that the RSS URL is wrong. No
fallback, guessed route or successful response is substituted for a failed gate.

Two repeated full live acceptances subsequently passed directly through EIS,
including the formerly 404 originals 0114100000126000011 and ...0012: actual
leased Worker succeeded, ten durable disposable SQLite rows searchable by
number/title, regional/keyword/exclusion filtering and replay deduplication,
two simulated notification dispatches. See ingushetia-eis-fixed-live-20261019.txt.
Fabrikant independently passed with 2390, 2391, 2364. Crossfeed repeated:
four source rows, two unique identities, both Worker jobs succeeded, zero
repeat EIS alerts. These are current live acquisitions, but no newly published
identity between polls is proven. Conservative regional coverage is unchanged.

## Strict Linux CA path

The official gu-st.ru certificate was downloaded again with normal HTTPS
verification and its canonical DER matched the existing pinned SHA-256
(d26d2d0231b7c39f92cc738512ba54103519e4405d68b5bd703e9788ca8ecf31).
The new pinned_ssl_context loads ONLY that verified root into memory, preserving
CERT_REQUIRED and hostname checks. This avoids the earlier /dev/stdin curl-77
file-loading problem and does not install a system root. Rejected/changed roots
fail closed. A Linux-compatible context test checks that exactly one CA loads.
The existing GitHub-hosted Linux/Windows diagnostic now also executes the scoped
CA probe; its network status is observational and must be read from its output,
not inferred from a green diagnostic job. Windows pinned-context live result:
HTTP 200, 200 law-verified feed rows. Linux network success remains to be checked
in the new run; a certificate fix cannot resolve a network timeout.

## Safe CI and remaining delivery gate

Use the existing GitHub-hosted jobs for this branch first: disposable hosted
VMs, contents:read, no checkout credentials or Telegram secrets in the live
source job. No self-hosted listener is needed for that attempt. If their exact
EIS/Fabrikant URLs remain unreachable, use the separately reviewed isolated
one-job VM design in pr226-isolated-runner-review-20261019.md only AFTER explicit
operator permission. No VM was provisioned, no new self-hosted runner registered,
and VALYQON-RU-01 remains untouched. Required live checks remain enabled.
Official hosted runner reference:
https://docs.github.com/en/actions/reference/runners/github-hosted-runners

Repository secret-name and variable-name inventories were empty. A separate
bot is possible: create it with @BotFather, save its token as the dedicated
TEST_TELEGRAM_BOT_TOKEN secret (never reuse production BOT_TOKEN), and supply
TEST_TELEGRAM_CHAT_ID for an explicitly authorized test recipient. For a private
chat the user must first start that bot; for a test group add the bot and permit
sending. Run only reviewed code with this secret, isolated temporary SQLite and
synthetic test subscription, never production subscriptions. These are proposed
configuration names; the current acceptance intentionally does not consume them.
The existing monitor can use a separate aiogram Bot instance with that token.
Official setup: https://core.telegram.org/bots/features#botfather
Official sendMessage contract: https://core.telegram.org/bots/api#sendmessage

Required evidence is the real API response with matching test chat and a
message_id, plus the recipient's confirmation that the alert appeared. Telegram
API acknowledgement alone is not proof the user read it. No bot token/chat was
provided, no Telegram request was sent, and simulated acknowledgements do NOT
satisfy delivery. Keep PR draft/unmerged until required CI and real delivery
conditions pass.

Local verification: 78 focused contracts, 141 Worker/jobs/monitoring regressions,
102 shared EIS/law/catalog regressions passed. Initial mistyped test filename
produced no tests; corrected invocation passed. No failure was counted as success.

## Hosted CI for code commit 7992ebf

- Russian source contracts: PASS, run 39308646072.
- Required Ingushetia strict contracts: PASS, run 39308646160.
- Required live Worker gate: FAIL in that same run. EIS ConnectError;
  Fabrikant ReadTimeout. No certificate verification code reported.
- Diagnostic run 39308646107: completed. Its green job status is observational.
  Both Linux and Windows pinned-root probes report BLOCKED / ConnectTimeout,
  strict_tls=true, hostname_check=true, trust_source=verified_pinned_root,
  certificate_verify_code=null. This verifies CA loading on Linux but does NOT
  establish a successful Linux TLS handshake or HTTP/card/Worker acquisition.

Run links:
https://github.com/Ramzes2023/TenderLens-AI/actions/runs/39308646072
https://github.com/Ramzes2023/TenderLens-AI/actions/runs/39308646160
https://github.com/Ramzes2023/TenderLens-AI/actions/runs/39308646107

The remaining Linux problem is network/handshake reachability without a
certificate-specific error. Full Linux acceptance and genuine Telegram delivery
remain open. No red checks were removed or converted to success. No merge.
