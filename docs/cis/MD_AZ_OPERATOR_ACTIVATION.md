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
