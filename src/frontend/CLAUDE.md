# CLAUDE.md

This file is read automatically by Claude Code at the start of every session in this repo. It tells Claude (and any human reading this) how this project works and what rules to follow. Keep this file at the **root of the repository**.

---

## What this project is

**The Archivist** — an AI assistant for the SLIIT Codefest 2026 AI Competition, Sub-track 1C ("Searching the Way a Human Does"). It answers questions over the Ashen Era Archive corpus using a 3-agent loop (Planner, Critic, Synthesizer) built on top of RAG retrieval (Chroma vector search + NetworkX knowledge graph), with a trust/contradiction layer as the core differentiator.

Full technical details: `docs/architecture.md`. Read that file before writing any backend code.

---

## Current phase

We are in **Phase 1: frontend only, with mock data.** No real backend exists yet. If you're helping with frontend work right now:
- Use the exact mock JSON shape defined in `docs/architecture.md` section 6 — do not invent a different response shape, the real backend will match this shape exactly later.
- Do not attempt to call a real API. There isn't one yet.

**Phase 2** (starts once the team splits up): all 4 members build backend components in parallel (ingestion, agents, graph, bot, eval). The person building frontend also joins backend work at this point.

---

## Hard rules — do not break these

1. **Never hard-code API keys or secrets in source files.** Always use environment variables loaded from `.env`. `.env` must be in `.gitignore`. Judges review full commit history — a leaked key in an old commit counts against us even if removed later.
2. **The corpus folder is read-only.** Never write to, rename, or restructure files inside the provided Ashen Era Archive corpus. Ingestion scripts only read from it.
3. **Only use free-tier tools.** No paid API calls, no paid services. If a tool's free tier runs out, use exponential backoff and rotate to a different team member's key rather than paying.
4. **Follow the API contract exactly** (`docs/architecture.md` section 6). Don't change the response shape without updating that doc and telling the team — frontend depends on it staying stable.
5. **Every retrieved fact must carry its source and trust tier.** Never present an answer without citing where it came from. Never silently resolve a contradiction between sources — surface it.
6. **Cap agent loops at 5 search hops.** No unbounded loops — this protects both API budget and demo reliability.
7. **Commit often, with clear messages.** Judges score git discipline. Avoid single giant "final commit" dumps — commit as you actually build, in small working steps.

---

## Coding conventions

- **Backend:** Python 3.11+, FastAPI, type hints where practical, one function = one responsibility (see `src/backend/agents/` — each agent is its own small file, not one giant orchestrator function).
- **Frontend:** React + Vite + Tailwind. Keep components small. Mock data lives in one clearly-named file (e.g. `src/frontend/mockData.js`) so it's easy to delete later.
- **No heavy agent frameworks** (no CrewAI, no AutoGen, no LangGraph) unless someone on the team already knows one well. Plain Python functions and a loop are enough for 3 agents and easier to explain live to judges.
- Add a short docstring to every function that isn't obvious from its name — judges and teammates should be able to read the code without asking you.

---

## Required repository structure (for the final ZIP submission)

Maintain this structure as we go — don't scramble to build it at the last minute:

```
<Team_Name>.zip
├── .git/
├── README.md
├── docs/
│   ├── architecture.md
│   ├── decisions.md
│   ├── limitations.md
│   └── diagrams/
├── src/
├── ai_usage/
│   ├── ai-usage-disclosure.md   # mandatory
│   ├── skills/
│   ├── claude.md                # copy of this file, saved here at submission time
│   └── context.md
├── configuration-example/
└── submission_report.pdf
```

Notes:
- This `CLAUDE.md` lives at the repo root for Claude Code to actually use it during development. Copy it into `ai_usage/claude.md` right before zipping for submission — don't move it there permanently, or Claude Code will stop reading it automatically.
- `docs/decisions.md` and `docs/limitations.md` don't exist yet — start them early and add to them as you go (e.g. "we tried X, it didn't work because Y" goes in limitations.md the day it happens, not from memory two weeks later).
- `configuration-example/` should hold a `.env.example` file (keys named but empty) so judges can see what's needed to run the project without seeing real secrets.

---

## AI usage disclosure — do this continuously, not at the end

Per the competition rules, we must export full chat logs with any AI coding assistant (including this one) as plain `.txt` files into `ai_usage/`.

**Reminder to whoever is working with Claude Code:** export this session's chat log before ending significant work sessions, not just once at the very end. It's much easier to save logs as you go than to try to reconstruct two weeks of history on day 13.

`ai_usage/ai-usage-disclosure.md` should describe, honestly:
- which AI tools were used
- what for
- which decisions were made by the team vs. suggested by AI
Honest disclosure carries no penalty — vague or missing disclosure looks worse than admitting heavy AI use.

---

## When helping with this project, Claude should

- Ask which phase we're in if unclear (frontend-mock vs. real backend) before assuming an API exists
- Point out if a suggested change would break the API contract in `docs/architecture.md`
- Flag if a suggested library or service isn't actually free
- Prefer small, explainable code over clever code — every team member must be able to explain and modify any part of the submission on demand in the final round
