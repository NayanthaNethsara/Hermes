# AGENTS.md

Engineering conventions for Hermes by TheKade. These apply to everyone working
in this repository, human or agent.

## Code style

- **Folder structure.** Keep code inside the structure defined below. Do not
  introduce parallel layouts.
- **Self-explanatory code.** Clear, descriptive names and small,
  single-responsibility functions, so the code reads without external
  explanation.
- **Minimal commenting.** No comments or docstrings on functions, classes or
  modules unless a requirement is genuinely non-obvious.
- **No unnecessary abstractions.** No speculative or future-proofing code.
  Build only what is asked for.
- **No dead code.** No unused functions, unused imports, unreferenced variables
  or unreachable paths.
- **Design principles.** KISS, DRY and SOLID, without added ceremony.
- **Semantic styling.** In frontend code use semantic tokens (`bg-success`,
  `text-destructive`, `border-border`) rather than raw colors.
- **Consistent visual language.** One color language per signal. Never reuse
  the same palette for two different meanings in one view.

## Project rules

- Secrets live in `.env`, never in source. `.env` stays gitignored.
- The raw archive under `data/raw_archive` is read-only. Ingestion reads from
  it and never writes back.
- Every answer carries its sources. Contradictions between sources are
  surfaced, never silently resolved.
- Changing a response shape means updating [docs/api.md](docs/api.md) and the
  frontend types in `src/frontend/types/hermes.ts` in the same change.
- Redis is optional infrastructure. Anything that touches it fails open.

## Repository structure

```
.
├── .env                        Local configuration, gitignored
├── AGENTS.md
├── README.md
├── Makefile
├── docker-compose.yml
├── configuration-example/
│   └── .env.example
├── data/
│   ├── raw_archive/            Source corpus, read-only
│   └── extracted_assets/       Figures and tables written by ingestion
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── setup.md
│   └── configuration.md
├── scripts/
│   └── preprocess_visuals.py
└── src/
    ├── backend/
    │   ├── main.py             FastAPI app, middleware, static mounts
    │   ├── agents/
    │   │   ├── graphs/workflow.py
    │   │   ├── nodes/          guardrail, planner, retriever, arbitrator, synthesizer
    │   │   ├── state/          Graph state models
    │   │   ├── llm.py          Chat model factory with provider fallback
    │   │   ├── prompts.py      System instructions and prompt builders
    │   │   ├── router.py       Ask and session endpoints
    │   │   ├── service.py      Graph invocation and SSE streaming
    │   │   ├── sessions.py     Session persistence, titles, summaries
    │   │   └── stream.py
    │   ├── core/               config, database, redis, rate_limit, logging, exceptions
    │   ├── ingestion/          parser, chunker, embedder, vision, schemas
    │   ├── retrieval/          vector_store, reranker, router, schemas
    │   └── workers/            run_ingest.py, run_query.py
    └── frontend/
        ├── app/                / redirect, /chat, /chat/[sessionId]
        ├── components/         hermes-app, chat-panel, chat-sidebar, answer-card, modals
        ├── lib/                api client, constants, validation
        └── types/hermes.ts     Shared response types
```

## Working in the backend

Python 3.11+, FastAPI, async throughout. Graph nodes are one file each under
`agents/nodes/` and return a partial state dict; do not merge two nodes'
responsibilities into one function. Configuration flows through
`get_settings()` rather than ad hoc environment lookups.

## Working in the frontend

Next.js App Router with React and Tailwind. Session state and the SSE
connection live in `components/hermes-app.tsx`; presentation components stay
stateless where they can. API calls go through `lib/api.ts` so error handling
and validation stay in one place.
