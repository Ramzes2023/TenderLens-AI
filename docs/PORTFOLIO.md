# Portfolio notes — how to present TenderLens AI

## 30-second summary

TenderLens AI is a Python tender-intelligence platform. It monitors live ЕИС RSS feeds, accepts tender PDFs through Telegram or FastAPI, extracts structured facts with GigaChat, applies deterministic company-fit scoring, stores history/deduplicates in SQLite, and provides semantic document Q&A with multilingual FastEmbed embeddings and Qdrant. The API is containerized with Docker and covered by automated tests/CI.

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
Because that mixes uncertain interpretation with a high-impact business rule. TenderLens separates extracted facts from deterministic scoring and leaves the final decision to a person.

**Why Qdrant if the project is small?**  
It demonstrates a real vector-store abstraction and metadata-filtered retrieval while local mode keeps the demo operationally simple. The same conceptual boundary can move to Qdrant server/Cloud later.

**Why SQLite?**  
For a single-node portfolio MVP it is reliable, transparent and dependency-light. The repository explicitly prevents pretending it is the answer for multi-replica deployment.

**How do you reduce hallucination?**  
Strict structured schemas, JSON validation, bounded RAG context, page references, deterministic scoring outside the model, and explicit unknown values. These reduce risk; they do not make LLM output infallible.

**What would you implement next for production?**  
PostgreSQL + migrations, Qdrant server, proper auth/RBAC, rate limiting, observability, OCR, retention policies and more source adapters.

## Claims to avoid

Do not describe the current version as:

- an autonomous procurement decision-maker;
- a system that predicts winning probability;
- a legal compliance checker;
- a multi-tenant production SaaS;
- an OCR system;
- a crawler for every Russian tender platform.

The implemented feature set is already strong without overstating it.
