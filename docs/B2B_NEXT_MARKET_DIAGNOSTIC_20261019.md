# B2B first-party next-market listing research (diagnostic, NOT integration)

On 19 October 2026, official B2B `https://www.b2b-center.ru/search/`
returned HTTP 502 and the previous office-category listing timed out from
multiple independent clients and CI runners. The vendor's own
`https://www.b2b-center.ru/app/next/market-search/?from=0` separately
displayed an original public list with live-looking notice links and dates
under `/app/market-next/{slug}/tender-{number}/`.

This PR adds **only** a strict, read-only, same-host diagnostic of that
additional officially observed URL. It uses the existing bounded client
(HTTPS + strict TLS/SNI + public DNS/IP checks + no proxies/cookies/redirects,
one URL, one request, 2 MiB cap, 25-second timeout), records sanitized
metadata and counts of links matching the explicit original notice path,
and never persists a notice or sends a notification.

Do not infer that a syntactically matching anchor is an independently
verified native first-party purchase. The older feed mixes other platforms,
so a later alternative parser MUST distinguish upstream provenance,
unmodified identity, original organizer/title/deadline and currency and
demonstrate current Worker→SQL→tenant search→scoring with genuine records
before production enablement. Documents and authenticated details remain
out of scope. This diagnostic is run *after failure* of mandatory B2B real
scoring, so its own success cannot turn that failing workflow green.

As always: no merger with outstanding red live workflows and no fake green.
