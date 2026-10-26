# PR 226: local evidence and isolated CI proposal

No self-hosted runner was started, registered, relabelled or contacted. No
production service, Telegram credential or other Codex workspace was used.

## Observed evidence

The local Windows repeat in `ingushetia-local-windows-repeat-20261019.txt`
fetched the current Fabrikant committee listing using `placer_search_str=0608058533`,
ordered by publication time descending. It independently checked three original
cards: 0114500000826002390, 0114500000826002391, 0114500000826002364.
The real leased Worker persisted them in disposable SQLite; number/title
search, positive profile keyword/region, keyword exclusion, negative search,
replay deduplication and three isolated notification acknowledgements passed.
These are current upstream acquisitions, but the IDs are unchanged from the
previous report: discovery of newly published IDs between polls is NOT proven.
This organizer filter does not establish coverage of all Ingushetia buyers.

EIS regional RSS also returned HTTP 200 with strict pinned-root verification
(`ingushetia-local-eis-route-20261019.txt`). A separate live adapter fetch
accepted five region-corroborated numbers: 0114100000126000011,
0114100000126000012, 0114500000826002384, 0114500000826002383,
0114500000826002382. RSS availability alone does not prove original cards or
the complete EIS Worker chain. A subsequent original-card probe recorded HTTP
404 for the first two RSS originals (0114100000126000011 and
0114100000126000012), see `ingushetia-local-eis-originals-20261019.txt`.
The repeated full acceptance therefore still used Fabrikant, see
`ingushetia-local-windows-eis-retry-20261019.txt`.
The broader system-CA probe returned HTTP 404
on Windows with certificate and hostname checks enabled; this is a distinct
URL and result, not evidence of a certificate verification failure.

The existing failed GitHub run 39302569282 reports ConnectError on EIS and
ReadTimeout on Fabrikant. Run 39302569264 also shows ConnectTimeout on Linux
and intermittent access on Windows; some separate soap4 detail cards return
200, while soap4 listing routes return 404. They cannot substitute for current
discovery on the adapter's main host. These logs do not establish geography,
IP blocking or a missing CA as the cause. ConnectError is generic; ReadTimeout
means a response read exceeded its deadline; ConnectTimeout can include TLS
handshake time. No timeout or TLS bypass was added.

Diagnostics now retain failures even when another upstream succeeds, inspect
bounded cause/context chains and report certificate verification codes when
present, without exception text, URLs, payloads or tokens. The system-CA probe
now records the actual operating system instead of labelling Windows as Linux.

The offline suite passed all 75 tests, recorded in `ingushetia-local-contracts-20261019.txt`.
An oversized certificate test's automatically generated ID exceeded Windows'
32767-character environment variable limit. Short parameter IDs preserve all
original payloads/assertions and permit the same test to execute on Windows.

## Proposed alternative — NOT provisioned or approved for execution

Use a fresh disposable VM on a separate account/network, with tested access
to the exact official URLs before installing an Actions runner. No WSL, shared
Windows folders, host socket, Docker socket, other checkout, private route,
production peering, cloud instance credentials or production secrets. Deny
private/link-local/metadata destinations at the network layer, inbound access,
and access to other workloads. Prepare dependencies in a reviewed image.

Register just in time for one reviewed immutable commit, with `--ephemeral`,
`--no-default-labels` and a unique one-run label never used by existing queued
jobs. Scope repository/group access to this job; enforce workflow restrictions
where supported. Audit queued jobs and routing before bringing it online.
Keep registration credentials in an external controller, outside the guest's
job environment; do not give the job PATs, cloud credentials or Telegram tokens.
Use read-only contents permission, no OIDC, no persisted checkout credentials,
no shared caches. Pin reviewed actions/dependencies and the exact commit.
Preserve scrubbed logs externally and destroy the entire VM and disk after
one job or timeout, including failure. Deregistration alone does not wipe a VM.

Before any launch, provide concrete account/network policies, mount inventory,
metadata/private-route deny tests, runner-group/label routing, exact workflow
SHA, credential handling, destruction mechanism and cost limit for review.
The user explicitly requires safety confirmation before starting this runner;
the proposal does not satisfy that requirement by itself.

Official basis: https://docs.github.com/en/actions/reference/runners/self-hosted-runners
(ephemeral runners receive one job, then deregister; cleanup remains operator
responsibility; matching persistent runners can receive queued jobs).

## Remaining limits

No production proof, no real Telegram receipt and no merge. No authorized test
bot/chat pair was supplied in this session, so notification proof uses the
credential-free isolated sink. Keep the real live CI gate fail-closed until its
actual execution succeeds. The local success must not replace its result.
