# Archivist Backend

FastAPI backend and multi-agent reasoning orchestrator for The Archivist.

## Modules

- `agents/`: Planner, Critic, and Synthesizer agents.
- `retrieval/`: Chroma vector search and NetworkX graph search.
- `llm.py`: OpenRouter LLM client with automatic failover.
- `orchestrator.py`: Multi-hop search execution loop.
- `trust.py`: Source trust scoring and contradiction detection.
- `main.py`: FastAPI server exposing `/api/ask` and `/api/health`.
