# UAE Ministry of Finance — Current Federal Business Opportunities

**Official issuer:** UAE Ministry of Finance,
`https://mof.gov.ae/en/public-finance/government-procurement/current-business-opportunities/`.
Only the actual **Open tenders** table is ingested. Every accepted row
must have a valid numeric RFQ, non-empty federal agency and title,
real published Open Date and Close Date, an unexpired deadline and a
matching individual official `https://procurement.gov.ae/page.aspx/en/bpm/process_manage_extranet/{RFQ}`
link. The government detail URL is **referenced only**, never requested
by the Worker. No credentials or private registration/login data.

Verified anonymous HTTPS from GitHub Actions on 17 Oct 2026:
HTTP 200, nine linked official federal RFQs (e.g. 12764 from the
Ministry of Education; 12623 from Other Federal Spending). Source
may be temporarily empty; no fabricated opportunities or deadlines.

**Jurisdiction:** federal UAE only; not Dubai Government eSupply, Abu
Dhabi Procurement Gateway, Ras Al Khaimah, or the entire UAE tender
market. Private supplier registration may be necessary to participate.

## Operator controls

Production remains disabled by default. The service is registered
only when `VALYQON_ASIA_UAE_FEDERAL_ENABLED=1`. A trusted host must
have the existing database, migrations, queues, running supervised
`python -m app.jobs.worker --connectors` and approved scheduler.
In the same environment enable `VALYQON_ASIA_OPERATIONS_ENABLED=1`,
then run `python -m app.sources.asia_all --enqueue --source ae_federal_mof`
to create one idempotent job for the current UTC hour. Once the
worker succeeds, use
`python -m app.sources.asia_all --search 'licence' --source ae_federal_mof`
to query only stored public tenders without sending customer keywords
upstream.

Real upstream → queued Worker → isolated SQLite → stored tender search
and replay deduplication are mandatory CI checks before merge.
The command never deploys AWS services or guarantees automatic customer
emails. Without a trusted continuously running worker, scheduler and
authenticated tenant search, a GitHub merge alone is **not** 24/7
production operation. Keep old results until an explicit expiry policy
is verified; do not confuse original bidding deadline with archival
retention. Do not invent prices when RFQ listing does not publish them.
