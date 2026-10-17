# Public service status for the VALYQON AI pilot

- Public routes: `/status` (HTML), `/status.json` (machine-readable).
- The API tile reports the instance that served the status page, and database tile uses an actual read-only connectivity call.
- All external procurement sources and outbound e-mail/Telegram delivery remain **unverified** because no end-to-end probe or alert delivery was run by this route.
- Checkout is **not enabled**, not marked as healthy. The composite state is never fully green on configuration alone.
- No arbitrary HTTP outbound calls from the status endpoint. No credentials, source endpoints, tenant names or data are revealed.
- Responses disable caching, scripts, frames, forms and cross-origin destinations.
- A historical uptime percentage, public source-by-source incident records and `status.valyqon...` DNS/TLS remain **not implemented / deployment pending**. These require independent probes, persisted observations, an approved domain and external monitor.
- This is appropriate as a transparent pilot diagnostics page, **not** a production SLA.
