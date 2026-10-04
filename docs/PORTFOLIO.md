# Portfolio notes — how to present VALYQON AI

## 30-second summary

VALYQON AI is a Python tender-intelligence platform with authenticated Web accounts and shared organization workspaces. It monitors live EIS feeds, accepts tender PDFs through Telegram or FastAPI, extracts structured facts with GigaChat, applies deterministic company-fit scoring, isolates personal and organization tender/RAG data, supports owner/admin/member/viewer RBAC and invitation-based team onboarding, and provides semantic document Q&A with multilingual FastEmbed embeddings and Qdrant. The API is containerized with Docker and covered by automated tests/CI.

## What is technically strongest

### 1. AI is not used for everything

The LLM extracts/interprets unstructured document facts. Business fit scoring is plain Python with explicit weights and hard-stop rules. This makes the final score reproducible and testable.

### 2. RAG has real retrieval boundaries

Chunks retain page numbers, embeddings are generated locally, and Qdrant queries filter by owner + PDF hash. The LLM receives only retrieved bounded context, and the Telegram answer shows source pages.

### 3. Monitoring is separated from document truth

ЕИС RSS is treated as discovery metadata. It can quickly pre-filter opportunities, but the architecture does not pretend RSS contains enough detail for legal/commercial evaluation.

### 4. Duplicate cost is controlled

Exact PDFs are hashed with SHA-256. Previously processed documents can reuse stored analysis instead of making another full LLM request.

### 5. Deployment assumptions are explicit

SQLite and Qdrant local mode are a deliberate single-node MVP choice. The repository explains exactly what must change before horizontal scaling instead of presenting local file stores as production-cluster infrastructure.

## Useful interview questions and answers

**Why not let the LLM decide whether to participate?**  
Because that mixes uncertain interpretation with a high-impact business rule. VALYQON AI separates extracted facts from deterministic scoring and leaves the final decision to a person.

**Why Qdrant if the project is small?**  
It demonstrates a real vector-store abstraction and metadata-filtered retrieval while local mode keeps the demo operationally simple. The same conceptual boundary can move to Qdrant server/Cloud later.

**Why SQLite?**  
For a single-node portfolio MVP it is reliable, transparent and dependency-light. The repository explicitly prevents pretending it is the answer for multi-replica deployment.

**How do you reduce hallucination?**  
Strict structured schemas, JSON validation, bounded RAG context, page references, deterministic scoring outside the model, and explicit unknown values. These reduce risk; they do not make LLM output infallible.

**What would you implement next for production?**  
PostgreSQL + migrations, Qdrant server, structured audit events, distributed/edge rate limiting, observability, public HTTPS hardening, OCR, retention policies and more source adapters.

## Claims to avoid

Do not describe the current version as:

- an autonomous procurement decision-maker;
- a system that predicts winning probability;
- a legal compliance checker;
- a multi-tenant production SaaS;
- an OCR system;
- a crawler for every Russian tender platform.

The implemented feature set is already strong without overstating it.


## Two-minute technical walkthrough

Start at the Dashboard: a session identifies the account; membership and explicit
roles select the shared workspace. Company context is resolved on the backend,
not trusted from a browser-supplied owner ID. Legacy Telegram owners remain a
separate compatibility path.

Follow one PDF: bounded extraction feeds a provider-independent generation call;
a strict schema validates its JSON. Python scoring compares extracted facts with
the active company profile, keeping completeness separate from fit. SQLite keeps
structured results and the hash. Page-aware chunks are embedded locally and stored
in Qdrant; retrieval applies namespace/document filters before the LLM answers.

Then follow an invitation: its raw random token is shown once, a digest is persisted,
acceptance checks the account email and consumes it atomically. Explain why a UI
button is not authorization and why shared API keys are not tenant identities.

Close with the deployment boundary: Compose provides one API and one bot, not a
horizontal cluster. Each owns its local Qdrant index. A shared vector server and
PostgreSQL/migration tooling are prerequisites for the next scale step.

## Hard problems and trade-offs

| Problem | Current choice | Trade-off |
|---|---|---|
| Team isolation without breaking Telegram | Separate organization namespace and session-only organization APIs | Compatibility paths need explicit regression tests. |
| Replay and concurrent invitation acceptance | Expiry, SHA-256 digests and atomic consume | A raw unused invitation URL remains a secret. |
| Web-to-Telegram linking | Guarded owner migration; reject unsafe PDF/RAG moves | Not every established account can be linked automatically. |
| Local vector-store file locks | Separate API/bot Qdrant directories | Shared SQL history does not mean shared retrieval indexes. |
| Uncertain document interpretation | Validation, unknown values, bounded context and human review | Correct JSON is not proof of factual accuracy. |
| Affordable local setup | SQLite + Qdrant local + CPU embeddings | Single-node operation and model-download/setup costs. |

## More interview questions

**Does a viewer-only button state protect data?** No. Backend membership and role
checks are authoritative; the UI merely reflects them.

**Can an integration API key access every organization?** Organization APIs require
a Web session and membership. Legacy keys support personal/integration compatibility,
not organization identity.

**Are team notifications running in the background?** Organization scans are on-demand.
Background organization notifications remain backlog; personal Telegram subscriptions exist.

**What comes after a single-node HTTPS deployment?** The public Compose edge already
provides Caddy HTTPS, security headers and trusted proxy configuration. Multi-node
operation would require PostgreSQL with migrations and Qdrant server. Shared throttling,
structured audit events, monitoring, backup/restore drills, retention and secret rotation
remain operational work; HTTPS alone does not establish those capabilities.

Present this as a working engineering portfolio project. Describe your actual role
and AI-assisted development honestly; do not claim customers or employment experience
that this repository cannot establish.
