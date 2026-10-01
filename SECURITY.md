# Security notes

TenderLens AI v1.0.0 is a portfolio/single-node MVP. These notes describe what is protected, what is persisted, and what must change before an internet-facing production deployment.

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

## API exposure

Default Docker bind is `127.0.0.1`; keep it that way for a laptop demo.

For any non-local exposure:

1. set `TENDERLENS_API_KEY` at minimum;
2. terminate HTTPS at a trusted reverse proxy;
3. add real user authentication/authorization;
4. add rate limiting and request-size controls at the edge;
5. define retention/backups and secret rotation;
6. move local SQLite/Qdrant state to server-backed services before scaling replicas.

The current API key is a shared secret, not tenant authentication.

## Telegram

Telegram user IDs scope history and RAG retrieval in the bot flow. This is application-level scoping, not a general multi-tenant security model.

## Logging

The bot redacts known token/proxy secrets and suppresses verbose vendor HTTP logs. Application code should not log document bodies, Authorization headers, `.env` contents or upstream error payloads that may contain secrets.

## Procurement safety boundary

TenderLens does not submit bids or make the final participate/do-not-participate decision. RSS data is pre-filter metadata. LLM-extracted facts, scores and RAG answers must be checked against authoritative tender documents before commercial/legal action.
