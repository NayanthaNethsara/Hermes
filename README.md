# The Archivist — Hermes

An AI research assistant that answers questions over the Ashen Era Archive by
searching the way a human would: planning searches, weighing how much each
source can be trusted, and surfacing contradictions between sources instead of
quietly picking a side.

Built for SLIIT Codefest 2026, AI Competition **Sub-track 1C** ("Searching the
Way a Human Does") as primary, and **Sub-track 1B** ("Connecting Facts Across
Thousands of Pages") as secondary.

## What It Does

A question flows through a LangGraph agent pipeline with conditional routing:

```
User → Guardrail → Planner → Retriever → Arbitrator → Synthesizer → User
              ↘ (greeting) ────────────────────────────↗
```

- **Guardrail** classifies intent — greetings skip retrieval entirely
- **Planner** rewrites follow-up questions into standalone queries using dialogue history
- **Retriever** runs hybrid vector + full-text search (pgvector RRF), cross-encoder reranking, and Redis caching
- **Arbitrator** detects factual contradictions across epistemic authority tiers
- **Synthesizer** streams a sourced, markdown-formatted answer via SSE

Every answer carries its sources with a trust tier (`high` / `medium` /
`medium-low` / `low`), the agent's search trace, and an explicit warning
when two sources disagree.

## Quick Start

```bash
# Prerequisites: Python 3.11+, Node.js 20+, Docker (for PostgreSQL + Redis)

# 1. Environment
cp configuration-example/.env.example .env   # fill in API keys

# 2. Infrastructure
make db          # PostgreSQL + Redis via docker-compose

# 3. Backend
make backend     # installs deps + starts uvicorn

# 4. Frontend (separate terminal)
make frontend    # installs deps + starts Next.js dev server
```

Open `http://localhost:3000/chat` — the app routes to `/chat/<sessionId>` automatically.

See [docs/SETUP.md](docs/SETUP.md) for the full step-by-step guide.

## Docs

| File | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | System design, agent graph, data flow, and API contract |
| [docs/user-flows.md](docs/user-flows.md) | End-to-end user flow diagrams for all interaction paths |
| [docs/SETUP.md](docs/SETUP.md) | Getting it running, plus troubleshooting |
| [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md) | How to verify answer quality |
| [docs/decisions.md](docs/decisions.md) | Choices made along the way and why |
| [docs/limitations.md](docs/limitations.md) | What's known to be weak or untested |

## Layout

```
src/
├── backend/        FastAPI app, LangGraph agents, retrieval, trust layer
│   ├── agents/     Graph nodes (guardrail, planner, retriever, arbitrator, synthesizer)
│   ├── core/       Config, database, Redis, rate limiting, logging
│   ├── ingestion/  Corpus parsing, chunking, embedding
│   └── retrieval/  Vector store, reranker, schemas
└── frontend/       Next.js App Router UI
    ├── app/        Route pages (/, /chat, /chat/[sessionId])
    ├── components/ Chat panel, sidebar, answer cards, modals
    └── lib/        API client, constants, validation
data/               Ingested corpus data (gitignored)
docker-compose.yml  PostgreSQL + Redis container orchestration
```
