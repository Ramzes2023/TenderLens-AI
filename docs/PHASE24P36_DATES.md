# 24P.3.6 date evidence and shared deadline predicates

Scope: offline, verified-data contract checkpoint only. No aggregate API, historical
union construction, chart, UI drilldown or Phase 24P.3.7/3.8/4 implementation.

## Evidence audit before implementation

Audited normalization.py, all ten adapters and their existing source tests, the
24P.3.1-5 registers, discovery/history/Saved schemas, opportunity JSON validation,
preview provenance and durable scoring storage. The prior retrieval checkpoint is
PARTIAL; its cursor, authorization, revision and storage limitations remain intact.

| Adapter | Existing raw evidence | v1 interpretation |
| --- | --- | --- |
| SAM.gov | postedDate; responseDeadLine / reponseDeadLine | ISO day or offset timestamp; naive timestamp ambiguous |
| TED | publication-date; selected existing deadline fallback, sometimes JSON list | ISO scalar or singleton list; multiple values ambiguous, original entire list retained |
| UK FTS | release date; tender.tenderPeriod.endDate | ISO offset timestamp; release date retains release_date semantics |
| AusTender | detail.Publish Date; rss.pubDate; decoded detail.TimeZone.CloseDateTime; detail.Close Date & Time | English d-Mon/Month-Y calendar publication; RFC RSS instant; decoded m/d/Y clock and English display clock ambiguous without verified source timezone; ACT display text is retained, not guessed as an IANA identifier |
| ZA eTenders | date_Published; closing_Date | ISO; only these paths enable existing documented SAST +02:00 adapter policy (za_etenders.py _SAST and _parse_local_datetime); date-only remains calendar date |
| CanadaBuys | publicationDate-datePublication; tenderClosingDate-appelOffresDateCloture CSV cells | ISO calendar publication; fixture's naive closing clock ambiguous; region is not timezone evidence |
| NZ GETS | item.pubDate; item.description.Close date | RFC offset publication; English weekday d Month Y 12-hour AM/PM or 24-hour clock with explicit numeric offset |
| India CPPP | listing.Published Date; listing.Bid Submission End Date | evidenced d-Mon-Y 12-hour AM/PM; existing IST +05:30 adapter policy (_IST and _parse_datetime); no policy for other paths |
| KZ | publish_date; end_date | ISO-like space-separated naive clock ambiguous; no historical or current country-based timezone guess |
| EIS | actual lowercased publication XML local-name path (pubdate); description.deadline | ISO or pubdate RFC (also explicit pubDate alias); only description.deadline enables dd.mm.yyyy calendar or dd.mm.yyyy HH:MM ambiguous clock; updated fallback retains source_update semantics |

Fixtures are existing offline source-shaped tests, not new live captures. These
source-local offset policies reproduce established adapter documentation and
fixtures, not an independently performed live/legal timezone audit. No current
country timezone rule is applied retrospectively to KZ, Canada or AusTender.
English month/AM-PM parsing is independent of process locale.

Distinct clocks: source published_at is not a search. H.created_at is the
persisted discovery/search event (UTC convention, seconds). Preview scored_at is
actual per-item scoring calculation; R.calculated_at is fenced materialization,
not retroactively a per-item calculation. Enrichment.observed_at is parser
observation, NOT synchronization. Opportunity first_seen/last_seen are UTC store
sync observations; scheduler sync_window is a scheduling bucket. None supplies a
missing deadline or publication. Explicit TimeField types keep these apart; pure
deadline predicates reject every non-deadline field. Existing stored clocks and
database conventions are unchanged; no raw legacy naive timestamp is upgraded.

## Versioned contracts and compatibility

`app/analytics/dates.py` defines immutable typed NormalizedDate, CalendarDate and
UTCInstant. Policy `source-date-v1` preserves exact JSON raw value, source, path,
field, semantics, parsed type, precision, offset evidence/seconds, status and
reason. UTCInstant requires aware UTC; CalendarDate rejects timestamp input and
offset evidence. Missing, invalid, ambiguous and unsupported carry no parsed
instant/date. Empty is missing; numbers/bools/objects invalid. Strict evidenced ISO
forms support Z, positive/negative colon offsets, minutes/seconds and fractions up
to six digits. Larger fractions are unsupported rather than silently truncated;
minus-zero offsets remain ambiguous. Invalid leap days/clocks/offsets fail closed.
No machine-local time or implicit now enters normalization.

New adapter enrichment adds `dates.<field>.normalized`; existing date-entry value,
path, status, display_value, raw_status and semantics remain byte/value compatible.
The old reported_unparsed status describes the legacy evidence entry; authoritative
parse status is explicitly the nested versioned normalized.status. Every new
normalization is recomputed during NoticeEnrichment validation. This detects
inconsistent sidecars, not authenticity of browser-submitted Saved content.
Normalized contracts are also exported by analytics/normalization.py.

Old entries without normalized metadata and future policy versions still decode
unchanged. `stored_date` reports unsupported with legacy_or_unknown_policy_unavailable
instead of reinterpreting their raw or adapter-normalized published_at/deadline.
Inconsistent v1 sidecars are unavailable (stored_evidence_mismatch); schema validation
rejects forged v1 data. Original snapshots, JSON decoding, observed_at, scores,
history, Saved, PDF, revision bytes, GETs and storage semantics are preserved. No
relational schema change, backfill, re-fetch, re-score or migration is required.

## Deadline and bucket policy

`app/analytics/deadlines.py` exposes pure `deadline-window-v1` decisions, grouping
and Discover-style filtering. One explicit server DeadlineWindow/as_of is supplied
once per selected population, normalized to UTC; no clock is read. W defaults to 7
and accepts only integer 1..366 (bool/string/fraction/zero/negative rejected).
Request timezone is retained separately from the supplied verified display IANA
timezone. Callers must authorize and choose that timezone/population first.

- Instant deadlines: UTC half-open [as_of, as_of + W elapsed days). Expired and
  exact end excluded. Valid instant membership works even without display zone data.
- Calendar deadlines: distinctly labeled W-calendar-day [local_day(as_of),
  local_day(as_of)+W). Today counts as a calendar day even after a possible unknown
  closing hour. No deadline instant, offset or closing hour is manufactured.
- Unknown kinds keep missing/invalid/ambiguous/unsupported separate; valid kinds
  distinguish instant/date_only and expired/closing_soon/future. Calendar windows
  and all date-cell replay are unavailable without actual ZoneInfo data. Unknown
  and non-IANA zones do not fall back to machine time or fixed offsets. Date range
  overflow is explicit unavailable; UTC membership is not changed by display failure.

DeadlinePopulation carries the selected population ID and organization/company
integrity labels. It MUST originate in already authorized server storage/search;
these labels are NOT an authorization token and never derive from request JSON.
Mixed org/company rows fail before predicates. No date filter touches authorization
or expands a selected population. Newest-revision/H union selection belongs to P3.7.
Identity is (source, external_id); identical duplicates count once; conflicting
duplicate deadline evidence is excluded with a diagnostic instead of selected by
input order. Deterministic sorted outputs expose states, duplicate count, conflicts,
selected identities, explicit unbucketed identities/reasons and typed
(instant/date_only, local date) cells. Mixed kinds
share a calendar cell only when a future caller explicitly unions the two identity
sets; neither may be counted twice. Grouping and filter_deadlines use the SAME
decision implementation, population and anchored window. Exact cell replay returns
the identical identity tuple. Display-timezone availability is explicit; absent
bucket data must not be presented as verified empty heatmap coverage.

The future aggregate API must retain scope, population ID, anchored as_of, W,
request/display timezone, both policy versions, kind and exclusion diagnostics.
Secure membership/cursor checks must precede these pure predicates on every read.
No GET endpoint, aggregate service, cache, job, network call or UI consumer is added.
Endpoint/chart/Discover end-to-end acceptance is downstream P3.7/P3.8/P4 PENDING.
24P.3.3 remains PARTIAL; 24P.2 real-browser acceptance remains PENDING.

## Validation

Final counts and exact commands are recorded in PHASE24_PROGRESS.md. Focused tests
include original fixtures for all ten adapters, legacy/new JSON, forged evidence,
scope integrity, pure no-IO/no-scoring/no-mutation, half-open microsecond boundaries,
local midnight, spring/fall DST, fold instants, duplicate/conflicting identities,
heatmap/filter reconciliation and explicit missing ZoneInfo behavior. Existing
retrieval/auth/Saved/PDF/scoring regressions provide runtime boundary protection.
Europe/Rome and UTC IANA data are present locally: DST cases executed on real
ZoneInfo; an independently injected unavailable loader verifies offline fallback.
No network/browser, secret/config reads, installs, real DB, production, staging,
commit, push, deploy or existing .tmp-phase24 directory operations occurred.
