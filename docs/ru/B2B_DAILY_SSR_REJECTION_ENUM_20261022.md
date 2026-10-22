# B2B daily real-source schema diagnostic — 22 October 2026

Scheduled run 39755035983 was RED on 22 October 2026 even after a genuine
rerun. First attempt: real B2B Worker acquired 10 current first-party SSR
notices and stored/queried 10, but the second independent scoring ingestion
failed at a permanent Worker error. Rerun: first Worker attempt also failed.
The one-request read-only diagnostic got HTTP 200 official HTML but
`ssr_native_schema=rejected`, with 0 verified native notices. A separate
21 October run showed 10 verified from the same site.

The existing diagnostic emitted only SourceError *class*, hiding which
strict parser invariant changed. Its new output is a fixed enum for known,
code-controlled parser messages (deadline cardinality, date, price,
identity, URL provenance, duplicate, etc). Unknown exception texts are never
logged. The daily workflow now invokes the same no-credential read-only
diagnostic `if: failure()` **after** both mandatory live Worker and
authenticated scoring steps. It diagnoses whichever step fails, but cannot
change a red status to green. No allowlist, HTTP/TLS/peer-IP policy,
request budget, parser acceptance, source activation, production data, or
customer Telegram delivery is changed.

Do not merge just because the diagnostic passes offline tests. The
source's real Worker→SQLite→query→authorized scorer must be fully GREEN on
the exact PR HEAD; if changed upstream SSR fields cause persistent failures,
repair only with genuine first-party evidence and adversarial contracts.


### Bounded real-source recovery — 22 October

Strict diagnostics on actual hosted runs demonstrated fluctuating Vue SSR
results: original HTTPS returned 200 but one response had rejected URL
provenance, while a follow-up diagnostic fetched an independently valid
20-card list. To avoid permanent failure on the first malformed response,
`B2BCenterSource` is now allowed **one same-URL replay** after a full
`SourceError` parse rejection. It consumes the existing second HTTP
request budget (no increase), clears the first response's cookies, reuses
strict pinned TLS/public-IP transport, and accepts only if the WHOLE second
response passes the exact same production parser. No third request, no
cross-platform or office fallback, no acceptance of mixed malformed cards.
Two invalid pages still fail RED, as proven by hostile offline tests. Live
Worker/SQLite/authorized scoring cannot be skipped.
