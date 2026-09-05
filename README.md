# The Archivist

An AI research assistant that answers questions over the Ashen Era Archive by
searching the way a human would — planning searches, weighing how much each
source can be trusted, and surfacing contradictions between sources instead of
quietly picking a side.

Built for SLIIT Codefest 2026, AI Competition Sub-track 1C ("Searching the Way
a Human Does").

## What it does

A question goes through a loop of three small agents on top of a retrieval
layer, capped at 5 search hops:

**Planner** (what should we search next?) → **Retriever** (Chroma vector search
+ NetworkX knowledge graph) → **Critic** (is this enough? do these sources
conflict?) → repeat, or hand off to the **Synthesizer** to write the answer.

Every answer carries its sources with a trust tier (`high` / `medium` /
`medium-low` / `low`), the agent's own search trace, and an explicit warning
when two sources disagree.

Two front doors, one backend: a three-panel Next.js web UI and a Telegram bot.

## Setup

**See [SETUP.md](SETUP.md)** for the full step-by-step — API keys, environment,
ingestion, and running each piece. Short version: copy
`configuration-example/.env.example` to `.env` at the repo root and fill in
your keys.

Read [SETUP.md § API budget](SETUP.md#api-budget) before a heavy testing
session — the OpenRouter free tier is the tightest constraint in the project.

## Docs

| File | What's in it |
|---|---|
| [docs/architecture.md](docs/architecture.md) | System design, request flow, data model, and the frozen API contract (section 6) |
| [docs/diagrams/architecture.md](docs/diagrams/architecture.md) | The same two diagrams as standalone files |
| [SETUP.md](SETUP.md) | Getting it running, plus troubleshooting |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | How to verify answer quality is good enough to submit, without more coding |
| [docs/decisions.md](docs/decisions.md) | Choices made along the way and why |
| [docs/limitations.md](docs/limitations.md) | What's known to be weak or untested |
| [docs/BUILD_PROMPTS.md](docs/BUILD_PROMPTS.md) | The build prompts each component was written from |

## Layout

```
src/
├── backend/       FastAPI app, orchestrator loop, agents, retrieval, trust layer
├── ingestion/     corpus -> Chroma, and chunks -> knowledge graph (offline)
├── frontend/      Next.js three-panel UI
├── bot/           Telegram bot
└── eval/          batch question runner
data/              Chroma DB + knowledge graph (generated, gitignored)
```
