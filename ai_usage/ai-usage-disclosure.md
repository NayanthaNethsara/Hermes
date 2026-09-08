# AI Usage & Governance Disclosure

## 1. Overview

This document discloses the use of Artificial Intelligence (AI) tools, Large Language Models (LLMs), and agentic development assistants during the engineering of **Hermes by TheKade** for the Intelligent Document Assistant challenge (Ashen Era Archive).

---

## 2. Tools & Models Used

| Tool / Service | Model / Version | Purpose |
|---|---|---|
| **Google Antigravity** | Agentic Coding Assistant | End-to-end software development, architectural implementation, LangGraph workflow construction, Next.js frontend engineering, automated refactoring, and AST code audits. |
| **Google Gemini** | Gemini 3.8 Flash High / Gemini Flash Thinking | Domain research, RAG strategy formulation, epistemic hierarchy design, prompt engineering, and multimodal extraction validation. |
| **Google Gemini (Runtime)** | `gemini-2.5-flash` | Runtime node execution across the LangGraph state machine: Contextual Query Planner, Sufficiency Critic, Epistemic Arbitrator, and Markdown Answer Synthesizer. Also powers offline multimodal plate and scanned document extraction (`vision.py`). |
| **Voyage AI** | `voyage-multimodal-3.5` & `rerank-2.5` | High-dimensional multimodal embeddings (1024-dim) for text and visual plate chunks, plus cross-encoder candidate reranking. |
| **OpenRouter API** | `google/gemini-2.0-flash-exp:free` | Fallback language model provider when direct GCP/Gemini credentials are unavailable. |

---

## 3. Engineering Constraints & AGENTS.md Compliance

All AI-assisted development was strictly governed by the repository engineering conventions defined in [AGENTS.md](../AGENTS.md):

1. **Self-Explanatory Architecture**:
   - Every function and class is built with small, single-responsibility logic and descriptive names (`assess_sufficiency`, `arbitrate_evidence`, `hybrid_search_rrf`), avoiding unnecessary explanatory comments or docstrings unless requirements were genuinely non-obvious.
2. **Zero Dead Code**:
   - The codebase is continuously audited via Python AST analysis and TypeScript strict mode. All unused imports, unreferenced variables, dead branches, and obsolete prototypes are pruned immediately.
3. **No Unnecessary Abstractions**:
   - Adherence to KISS, DRY, and SOLID principles without speculative abstractions.
4. **Read-Only Corpus Guarantee**:
   - The raw corpus in `data/raw_archive/` is treated as strictly read-only. Offline ingestion and visual pre-processing never alter or overwrite archive source files.
5. **Fail-Open Optional Infrastructure**:
   - Redis caching and PostgreSQL checkpointers fail open. When services are temporarily down, the system degrades gracefully (falling back to direct DB queries and `MemorySaver`) without crashing the application.
6. **Contradiction Transparency**:
   - The epistemic arbitrator isolates and surfaces genuine source contradictions rather than silently resolving them or hallucinating consensus.

---

## 4. Human Oversight and Quality Assurance

- **Verification**: Every node transition, query decomposition, and vector retrieval strategy was verified against the competition development set (`sample_questions.json`) across Sub-tracks 1A (Rich Answers), 1B (Connecting Facts), and 1C (Searching the Way a Human Does).
- **Code Reviews & Audits**: AST import scans (`compileall`, custom AST parser) and frontend static typechecks (`npm run lint`, `npm run build`) were run repeatedly to guarantee production build integrity.
- **Security & Secrets**: Secrets, tokens, and GCP credentials reside exclusively in local, gitignored `.env` files and application default credentials. No sensitive keys are committed to source control.

---

## 5. Audit Trail & Exported Transcripts

Complete conversational trajectories and development logs are preserved in this directory for auditability:

| Transcript File | Scope |
|---|---|
| `chat_2026-09-08_011857.txt` | Initial scaffolding, repository setup, database schema |
| `chat_2026-09-08_160039.txt` | Ingestion pipeline, visual cataloging, multimodal embeddings |
| `chat_2026-09-08_165453.txt` | Graph node construction (planner, retriever, synthesizer) |
| `chat_2026-09-08_200921.txt` | Sub-track 1C search loop (critic, arbitrator, multi-hop routing) |
| `chat_2026-09-08_232303.txt` | UI refinement, contradiction banner redesign, error resolution |
| `chat_2026-09-08_234505.txt` | Final audit, dead code elimination, documentation updates |
| `chat_2026-09-08_project_restructure.txt` | Directory restructuring to conform with `AGENTS.md` layout |

Development chat sessions can be re-exported at any time using:

```bash
make export-chat
```
