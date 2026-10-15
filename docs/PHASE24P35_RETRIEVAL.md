# 24P.3.5 retrieval audit and verified subset — PARTIAL

Audit before implementation: H is `discovery_search_history`, an AUTOINCREMENT
event table with organization/company, writer account, UTC second-resolution
created_at, counts/source reports and the complete serialized discovery response.
The scoped repository already reauthorizes membership/company on every read.
Legacy list defaults to 50 and clamps to 100; single detail reads saved JSON.
There is no retention coverage register, immutable event enforcement, archived
deleted-event body or historical profile backfill. Persisted observations are not
lifetime activity. Existing fit/provenance policy remains preliminary-fit-v1.

R is account AND organization AND company private. scoring_snapshots freezes
profile digest/configuration/source scan counts; scoring_candidates maps ordinal
to immutable scoring_public_revisions. scoring_results retains scoring JSON and
fenced materialization time. Existing reads reject changed current profile.
Candidate selection is bounded to 500, scanning at most 1000 per source. Neither
run counts nor candidate counts claim all market opportunities. No schema change
is necessary for the implemented subset. No migration was performed.

Additive GET contracts:

- `/api/v1/organizations/{org}/companies/{company}/discovery/history-page`:
  page_size 1..20; optional offset-aware start/end normalized to UTC; [start,end)
  over persisted search time. Descending (created_at,id), frozen maximum ID and
  as_of, observed_count, read_count, has_more/next_cursor, population_cursor,
  completeness/storage states. Snapshots returned from storage with corrupt,
  missing, count mismatch and duplicate-identity diagnostics. Total is explicitly
  observed storage within the fence; lifetime_total is null. Microsecond query
  bounds round up to the next persisted second, preserving interval membership
  for the existing second-resolution writer. UTC storage convention is required.
- `.../discovery/history-snapshots`: population_cursor plus comma-separated ids
  (1..20), same page_size/start/end binding. Reauthorizes even empty/missing reads;
  reports duplicate requests, missing scoped records, corrupt/missing snapshots,
  count mismatch and out-of-watermark/query records. Other-tenant IDs disclose
  only missing_in_authorized_scope. Every lookup rechecks membership/company.
- `.../scoring/runs`: page_size 1..100, frozen ordered run-ID manifest up to 1000.
  Larger populations fail explicitly (409) and are never silently truncated.
  Missing runs and invalid/stale snapshot bindings are explicit states. Run status
  is observed on each read, not frozen historical job state.
- `.../scoring/runs/{job}/revisions`: existing authorized digest-checked result
  paging plus immutable notice bodies, revision, connector version, ordinal and
  calculated_at (fenced_materialization). Join uses snapshot AND ordinal AND
  revision; source/external ID is an integrity check, never a join to H/Discover.
  Missing/corrupt revision bytes are marked; pending runs return no bodies.

HMAC-SHA256 domain-separated cursors reuse the existing in-memory application
API key; no new secret, dotenv/config/credential reads. Missing key disables new
cursor reads with 503. Scope/account/query/page size and one-hour expiration are
signed; requests reauthorize storage access. Replaying a valid cursor repeats the
same read and is intentionally idempotent. Switching active company does not
change explicitly addressed scope; changing company path rejects the old cursor.
GETs issue no inserts, updates, scoring, jobs, source fetches, Saved/PDF changes.
Legacy GET history and scoring detail formats/defaults remain unchanged.

Exact blockers to COMPLETE:

1. General R populations above 1000 need durable server-side population storage
   or a verified insertion fence; existing UUID jobs and second timestamps alone
   do not exclude concurrent inserts with equal timestamps reliably. Current
   bounded manifest is a verified subset, not unlimited run-history acceptance.
2. H deletion between reads can only be detected by changed observed count; lost
   bodies cannot be retrieved. Direct modification of old event rows is not
   prevented by the schema. No durable retention/immutability proof exists.
3. Legacy history UI still uses its original limited list; new complete paging is
   an additive server API. A paginated UI consumer is not delivered here.
4. Snapshot count/identity diagnostics do not establish unrecorded upstream
   completeness; old provenance stays historical/unbound. Noncanonical manually
   imported timestamps, response-byte limits and PostgreSQL runtime pagination
   acceptance are not verified by these SQLite offline tests.

24P.2 browser acceptance PENDING; 24P.3.3 PARTIAL; 24P.3.4 policy unchanged;
24P.3.6+ not begun. Next work is closing these 24P.3.5 blockers, before 24P.3.6.
No internet, installs, real-data migrations, production, staging, commit, push,
deploy or .tmp-phase24 directory changes. Existing uncommitted work preserved.

Measured validation (guarded runner, overlapping selections, all exit 0):
p35-focused 53 passed; p35-broad 395 passed + 390 subtests (237.88s);
p35-final-focused 96 passed; p35-manifest-final 8 passed;
p35-acceptance-final 8 passed; p35-final-scoring 50 passed (24.56s).
The broad run predates final narrow additions; final narrow runs cover changed
retrieval behavior. Six existing JS suites pass. compileall and diff-check pass.
One existing Starlette deprecation warning, no skips in these selections.
Final error/storage rechecks p35-error-final and p35-storage-final: 8 passed each,
exit 0; the latter follows the snapshot query-length/missing-key guards.
