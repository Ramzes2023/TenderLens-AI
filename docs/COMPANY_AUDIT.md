# Tenant audit of Saved actions (migration 19)

Events are committed with the saved-tender transaction and include only:
actor account ID, company/org, action, saved item ID, export row count and time.
No tender content, original PDF, private note, account email or sensitive query
parameters are written to this table. Saving a second time is `tender_refreshed`.

Export CSV/Excel audit records are inserted **after** successful serialization
and before returning bytes, with role/company authorization rechecked. The event
means **export generated**, not successful browser download or onward distribution.
A DB write failure prevents an unlogged export from being returned.

Owners/admins view the last 100 events via `GET /api/v1/organizations/{id}/activity`
or Saved → Recent company activity. Members/viewers cannot query this timeline.
The list is scoped again in the database, not only in the HTTP handler.

Rows are append-only through application methods, but a database superuser can
modify data. Therefore, this is a **durable application audit history**, not
cryptographically tamper-proof/compliance-certified immutable storage. Database
retention policy, archival and enterprise export logs require deployment and review.
SQLite→Postgres offline import and PostgreSQL 16 restore acceptance must be green.
