# CIS: operator-controlled Moldova / Azerbaijan procurement ingestion

## State
Source adapters `md_elicitatie` (independent accredited Moldova marketplace,
including municipal buyers) and `az_azeristilik` (official Azerbaijani heating
enterprise, **not** the national eTender API) are staged behind two **separate**
operator flags. Registration on its own **does not** create a polling schedule,
deploy anything to AWS, send tenant alerts, or enable either source in production.

## Operator go/no-go requirements
1. Check exact merge candidate HEAD: both real upstream list/detail → leased
   worker → disposable SQLite → stored search jobs green, along with full Linux,
   Windows, Docker and every required cross-source CI. **No exceptions.**
2. Deploy the reviewed merged commit through the normal release process, verify
   worker, database migrations, schedules and tenant search permissions.
3. Opt in separately using `VALYQON_CIS_MD_ELICITATIE_ENABLED=true` and/or
   `VALYQON_CIS_AZ_AZERISTILIK_ENABLED=true`. Default is `false`; an
   invalid value fails closed. Restart workers to reload config.
4. Through the *approved operator environment* enqueue with
   `python -m app.sources.enqueue --source md_elicitatie` or
   `python -m app.sources.enqueue --source az_azeristilik`. Observe queue
   completion via `python -m app.sources.enqueue --status <job-uuid>`.
5. Verify fresh source IDs and useful user search terms against persisted
   notices. Set the flags to `false` and restart on unexpected health failures.

The operator queue command only **enqueues** jobs. A separately running
worker must consume them and populate the configured database; public saved
search reads stored notices, it does not synchronously fetch websites.

## Safety
HTTPS only, source-specific allowed hosts and bounded request counts, no
redirects, cookies, proxy credentials, or TLS bypass. Distinct source IDs,
source provenance, duplicate fencing and tenant-search queries stay local.
An Azerbaijani tender *participation fee* is not the contract value and must
never be treated as such. Current validations are against disposable DBs,
not production activation.

## Reviewed one-shot source cycle (added after source merge)

The operator can invoke `python -m app.sources.enqueue --cis-approved` on the
**approved machine with the approved worker environment**. This runs no HTTP and
does not start a worker, database migration, scheduler or alert on its own. It
only creates durable jobs for the explicit allowlist
`md_elicitatie`, `az_azeristilik`, `az_adif_small` *when their respective*
`VALYQON_CIS_..._ENABLED=true` flags are set. When none are enabled, it
fails closed and creates no source jobs. Unlike a catch-all connector loop, it
**cannot** accidentally enqueue a newly registered or separately managed source.

The returned JSON maps source keys to `job_id` and `state`. A second call in
the same UTC hour reuses the existing source-specific job ID; after the hour
rollover a new durable job may be created. Worker retry/backoff and lease
fencing remain the responsibility of the existing job subsystem.

Operators may *separately* configure a **minimum hourly one-shot timer**,
for example a reviewed systemd timer or container scheduler, only after
production credentials, network egress and tenant-search checks are approved.
Merely merging this feature installs **no recurring timer**; no background
scheduler, crontab, secrets, production flags or AWS resources are modified.
Use a single schedule owner per deployment and monitor run exit code and
durable statuses to distinguish queued/running/succeeded/failed.

Run `python -m app.sources.enqueue --status <job-uuid>` for each returned ID,
then confirm records in the approved database by a real buyer-name saved search.
On operational failure, disable only the affected source flag, stop the
external schedule if appropriate, restart its worker, and preserve stored
notices and their provenance for audit. An already queued job still requires
explicit operator handling; flag changes do not retroactively delete it.

**ADIF cadence caveat:** the first verified quotations close on 19 October
2026; a genuinely empty currently-open batch is not evidence of a broken
website, nor is a successful stale-history query proof of fresh bids. Distinguish
last successful upstream fetch from current number of open tenders.
