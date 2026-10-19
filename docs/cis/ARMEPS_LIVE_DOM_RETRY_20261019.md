# Live official ARMEPS diagnostic: strict bounded timeout retry

The source's own `cis-am-live-dom-diagnostic.yml` can fail before it reads
its first HTML byte on an intermittent `httpx.ConnectTimeout`. On 2026-10-19
the workflow logged a bounded `ConnectorTransportError -> httpx.ConnectTimeout
-> httpcore.ConnectTimeout` chain. In a separate genuine CI run from B2B
the same first-party ARMEPS Worker saved 20 current original records and
completed a SQLite keyword search. **That success is not evidence that every
independent probe succeeded.**

The diagnostic now allows **at most three** network attempts, and retries
**only when** a transport error is marked retryable and the actual exception
cause chain contains an explicit HTTPX ConnectTimeout or ReadTimeout, without
any SSL failure or public-IP rejection in the chain. Each attempt constructs
an independent restricted FetchPolicy (exact `eauction.armeps.am`, HTTPS,
public-IP/peer and TLS verification, one GET, max 1 MiB, trust_env=False,
no redirects). Non-timeout statuses, SSL/policy problems or invalid HTML
fail immediately; if all three attempts fail, the workflow remains **RED**.
The existing real HTML parser still requires at least three current genuine
records before success. Offline synthetic tests verify retry bounds and
TLS/HTTP fail-closed but are never called live procurement proof.

This change does not touch the leased Worker, production source flags,
customer database, other CIS sources, Samara or Telegram. It does not justify
merging while any workflow check remains red. PR #157 is still a draft.
