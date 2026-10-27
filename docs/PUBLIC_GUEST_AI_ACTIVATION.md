# VALYQON public guest AI — operator activation and verification

## Why the web widget says "unavailable"

The guest form sends `POST /api/v1/public/help/ask`. The backend returns
`503` if either (a) `VALYQON_PUBLIC_AI_ENABLED` is off, (b) the provider
failed to configure, or (c) live inference fails. The browser displays the
same generic user-visible message for these cases. A screenshot **alone**
does not identify which of the three is happening on the server.

The reviewed `compose.public.yaml` intentionally forces
`VALYQON_PUBLIC_AI_ENABLED: "false"`, regardless of the VPS `.env`.
Setting only `.env` therefore **cannot** enable the existing public
deployment. This is intentional fail-closed behavior, not a frontend bug.

## Activation path (authorized production operator only)

The optional `compose.public-ai.yaml` is an explicit **operator-only**
overlay; it is not included in default startup and does not turn the AI on by
itself. It leaves the normal source, payment, Telegram and API exposure gates
untouched.

1. Confirm **a real server-side GigaChat account and budget**, a trusted TLS
   certificate and the provider's terms/privacy requirements. The current
   gateway supports `gigachat` as primary. Set these values securely in the
   private *server* environment (never in code, screenshots, CI, or chat):
   `VALYQON_AI_PROVIDER=gigachat`, `GIGACHAT_CREDENTIALS`,
   `GIGACHAT_MODEL`, and any required `GIGACHAT_SCOPE` /
   `GIGACHAT_CA_BUNDLE_FILE`. Keep secrets out of GitHub commits.
2. Confirm the provider is reachable **from the API container**, including
   outgoing HTTPS, DNS and the CA bundle path. `/health` reporting an LLM
   component as "ready" proves only **local initialization**, not successful
   real inference. Set a real *provider-side spending cap* and anti-abuse
   controls at the reverse proxy. Built-in limits are three queries per IP per
   ten minutes and 48 queries total per process per 24 hours. These counters
   reset on restart and are not shared across replicas.
3. In the private server `.env` (or secure server injection), set
   `VALYQON_PUBLIC_AI_ENABLED=true`. Verify that this is *not* enabled in
   website review or other public services.
4. After review and merge of this PR, run from the exact deployed revision
   on the trusted host:

   ```bash
   docker compose -f compose.public.yaml -f compose.public-ai.yaml up -d --no-deps --build api
   ```

   This recreates **only the API** using the explicit overlay. It must not be
   run by CI or on a VPS whose deployment layout/configuration hasn't been
   inspected first. Do not delete containers' data volumes or change
   `DATABASE_URL`.

5. Test a *single real answer* from an external browser or trusted host:

   ```bash
   curl -fsS -i https://valyqon.duckdns.org/health
   curl -i https://valyqon.duckdns.org/api/v1/public/help/ask \
     -H 'Origin: https://valyqon.duckdns.org' \
     -H 'Content-Type: application/json' \
     --data '{"question":"Как работает гостевой поиск VALYQON?"}'
   ```

   Successful acceptance: HTTP `200`, JSON with `scope:
   public_product_only` and a non-empty generated answer in `answer`.
   `503` means disabled, unconfigured, or an inference outage (inspect
   *sanitized* API logs on the host); `429` is an intentional budget
   rejection; `403` is an origin/security rejection. Do not send private
   account or tender data as test questions.

6. Watch sanitized error rates, quota consumption and provider usage for
   unexpectedly high costs. Rate limiting is process-local, so production
   public activation should also have a shared edge/provider budget and
   abuse protections.

## Rollback / fail-closed behavior

Remove the operator-only overlay from the running API deployment and recreate
the API using *only* the default public Compose:

```bash
docker compose -f compose.public.yaml up -d --no-deps api
```

The original public Compose forces `VALYQON_PUBLIC_AI_ENABLED=false`.
This rollback does not intentionally touch persistent databases or volumes.

## What this change does **not** claim

- GitHub code or passing unit tests do **not** prove that a real GigaChat
  account is configured on the VPS, that inference has succeeded, or that
  the public widget already works.
- The feature only explains public VALYQON product workflows: it cannot
  reveal private company profiles, document content, buyer identities or
  paid source URLs.
- This is a controlled single-node operator feature, not an authorization
  to launch unreviewed external sources, paid access, mass notifications
  or autonomous spending.
