# Security notes

TenderLens AI v1.5.0 is a single-node release with Web accounts, session authentication and Telegram identity linking. These notes describe what is protected, what is persisted, and what must still change before a public multi-tenant production deployment.

## Secrets

Do not commit or share:

- `.env`
- `TELEGRAM_BOT_TOKEN`
- `GIGACHAT_CREDENTIALS`
- `TENDERLENS_API_KEY`
- authenticated proxy URLs
- local database/vector-store files

`.gitignore` and `.dockerignore` exclude the main local secret/data paths, but operators remain responsible for checking commits and screenshots. If a token is exposed, rotate/revoke it at the provider rather than relying on deletion from chat/history.

## Stored data

- SQLite stores structured tender analysis, scoring metadata, hashes, timestamps and monitoring state.
- Qdrant stores RAG chunk text, page/chunk metadata and embeddings.
- Raw PDF bytes are not retained by the tender history pipeline.
- FastEmbed model files are cached locally.

Treat the whole `data/` directory / Docker named volume as application data that may contain sensitive tender text.

## External data processors

When GigaChat analysis/RAG generation is enabled, bounded extracted text or retrieved chunks can be sent to that external provider. Deployment owners must evaluate provider terms, retention and organizational compliance requirements before using confidential documents.

## Web authentication and sessions

- Registration/login use normalized email identities and scrypt password hashes; raw passwords are never persisted.
- Web sessions use high-entropy random tokens. SQLite stores only the SHA-256 token digest.
- The browser cookie is `HttpOnly`, `SameSite=Lax`, path `/`, and is marked `Secure` when the request is HTTPS.
- Expired sessions are rejected during lookup and are opportunistically deleted whenever a new session is created.
- Session-authenticated owner-scoped API calls derive the owner from the current account and reject another requested owner.

State-changing browser requests reject explicit cross-site provenance using `Origin` and `Sec-Fetch-Site`. This preserves non-browser/legacy API clients that do not send browser provenance headers; it is not a replacement for HTTPS/reverse-proxy controls.

Login failures use a bounded in-memory limiter (default 5 failures in 5 minutes per client/email key, maximum 4096 active keys). A successful authentication resets that key. Because this limiter is process-local, public multi-replica deployments still require reverse-proxy or shared-store throttling.

## API exposure

Default Docker bind is `127.0.0.1`; keep it that way until the dedicated public deployment phase.

For non-local/public exposure:

1. terminate HTTPS at a trusted reverse proxy and verify forwarded-host/proxy configuration;
2. keep `TENDERLENS_API_KEY` for integrations that need the legacy API path;
3. add organization membership, roles/permissions and audit boundaries before onboarding multiple customer teams;
4. enforce edge/distributed rate limiting and request-size controls;
5. define retention/backups and secret rotation;
6. move local SQLite/Qdrant state to server-backed services before scaling replicas.

The API key remains a shared integration secret, not tenant identity. Web session authentication is real user identity for the current single-node account model, but organization-level authorization is a later phase.

## Telegram

Telegram user IDs scope history and RAG retrieval in the bot flow. Web accounts start in a synthetic owner namespace. `Connect Telegram` creates a random one-time ticket with a 10-minute lifetime; only its SHA-256 digest is stored. Telegram deep-link redemption obtains the real `from_user.id`, atomically claims the ticket, and then performs the guarded owner migration. Reuse/expiry is rejected, a newer ticket invalidates the previous one, and a failed migration releases only its own claim marker.

Linking is deliberately blocked when owner-scoped PDF/RAG state cannot be migrated safely without also moving the external Qdrant namespace. This account/owner model is still application-level scoping, not the final Organizations/Roles multi-tenant authorization model.

## Logging

The bot redacts known token/proxy secrets and suppresses verbose vendor HTTP logs. Application code should not log document bodies, Authorization headers, `.env` contents or upstream error payloads that may contain secrets.

## Procurement safety boundary

TenderLens does not submit bids or make the final participate/do-not-participate decision. RSS data is pre-filter metadata. LLM-extracted facts, scores and RAG answers must be checked against authoritative tender documents before commercial/legal action.
