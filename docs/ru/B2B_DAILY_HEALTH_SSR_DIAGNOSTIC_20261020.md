# B2B daily-health incident — 2026-10-20

The main-branch scheduled RU genuine-source health run 39400374382 initially
failed on B2B: one Worker attempt ended with permanent_failure, without any
exception payload being exposed. The other four live source jobs passed.
A retry of **the same job at the same main SHA**, attempt 2, succeeded with
ten genuine first-party B2B SSR notices via a leased Worker, ten SQLite
search hits, and authorized scoring / tenant isolation. No production data or
Telegram delivery was involved. This proves an intermittent failure, but not
its precise root cause.

The old standalone Next-market diagnostic only counted ordinary hrefs with
no fragment and thus misreported zero native links on Vue SSR responses.
Update it to count **only notices accepted by the existing production SSR
parser** and report sanitized counts plus exception class, not URLs, titles,
HTML or customer details. All exact-host HTTPS/TLS, public DNS/peer-IP checks,
one-request/2MiB budget and no redirects/proxies remain unchanged.

Run the diagnostic as an additional `if: failure()` step immediately after
the mandatory daily real B2B Worker gate. **Do not add continue-on-error**,
disable live acceptance, or treat a diagnostic PASS as ingestion/scoring PASS.
A genuinely failed B2B live Worker must keep the overall daily health RED.
Tests assert the fail-closed workflow and the fact that an anchor alone is
not a verified native procurement.

Samara #191 remains separate and blocked for anonymous original details.
This change does not activate a source, deploy, merge, or send messages.
