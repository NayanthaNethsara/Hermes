# AI Usage Disclosure

## 1. Overview

This document outlines the use of Artificial Intelligence (AI) tools and Large Language Models (LLMs) during the development of The Archivist for SLIIT Codefest 2026.

## 2. Tools & Models Used

| Tool / Service | Model / Version | Purpose |
|---|---|---|
| AI IDE / Coding Agent | Antigravity / Claude | Architectural planning, scaffolding, refactoring, documentation |
| OpenRouter API | minimax/minimax-m2.7:free (and fallbacks) | Runtime agent reasoning (Planner, Critic, Synthesizer, Contradiction Detection) |
| Voyage AI | voyage-4-lite | Embedding generation for vector retrieval |

## 3. Scope of AI Assistance

- **Architecture & System Design**: Assistance in structuring multi-agent loops and trust evaluation pipelines.
- **Scaffolding & Boilerplate**: Generation of initial schemas, API wrappers, and type definitions.
- **Refactoring & Project Management**: Transitioning project structure to `pyproject.toml`, Dockerfiles, and container orchestration.
- **Documentation**: Drafting technical guides, architecture documentation, and setup instructions.

## 4. Human Oversight and Quality Assurance

- Every line of AI-generated code and configuration was manually reviewed, verified, and tested by team members.
- Architectural decisions, agent thresholds, fallback chains, and security practices were determined and validated by the team.
- Zero sensitive data or credentials were leaked or embedded into version control.

## 5. Chat Logs & Transcripts

Exported conversational logs and session transcripts are organized in this directory:

- Session logs will be exported and stored as `.txt` files in `ai_usage/`.
