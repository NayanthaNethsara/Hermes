# Build Prompts — The Archivist

Feed these into your AI coding assistant **one at a time, in order**, inside the project repo (so it can see `docs/architecture.md` and `CLAUDE.md`). Check each step works before pasting the next one.

---

### Prompt 0 — Project scaffolding

```
Set up the initial repository skeleton for a project called "The Archivist". Read docs/architecture.md and CLAUDE.md first if they exist in this repo.

Create this exact folder structure:

src/
├── backend/
│   ├── agents/
│   ├── retrieval/
├── ingestion/
├── frontend/
├── bot/
└── eval/
data/
docs/
ai_usage/
configuration-example/

Create:
- .gitignore that excludes .env, __pycache__/, node_modules/, data/chroma/, *.gpickle, and standard Python/Node ignores
- .env.example listing these keys with empty values and one-line comments: VOYAGE_API_KEY, OPENROUTER_API_KEY, OPENROUTER_BASE_URL (default https://openrouter.ai/api/v1), OPENROUTER_MODEL (default to a free model, ID ending in ":free"), TELEGRAM_BOT_TOKEN
- requirements.txt for the Python backend with: fastapi, uvicorn, chromadb, networkx, python-dotenv, requests, python-telegram-bot, pytesseract, pypdf, python-docx, tenacity (for retry/backoff)
- A minimal README.md with project name, one-sentence description, and a "Setup" section that says "see .env.example, copy to .env and fill in your keys"

Do not write any application logic yet. This is scaffolding only.
```

---

### Prompt 1 — Data ingestion pipeline

```
Build src/ingestion/ingest.py.

Goal: read the Ashen Era Archive corpus and load it into a Chroma vector database as searchable chunks.

Requirements:
- Take the corpus root folder as a CLI argument (--corpus-path), do not hardcode the path
- Walk the folder recursively, handle these file types: .pdf, .docx, .md, .txt, and scanned/image files (use pytesseract for OCR on images)
- Split each document's text into chunks of roughly 300-500 words, keeping paragraph boundaries where possible
- For each chunk, assign metadata:
  - chunk_id (unique string)
  - source_doc (original filename or title)
  - page (if known, else null)
  - source_type: one of "novel", "wiki", "codex", "ephemera" — infer this from the folder name or filename pattern, and print a warning listing any files it could not classify, so we can fix the classification rule once we see the real folder names
  - trust_tier: map source_type to trust_tier using this exact table:
    codex -> "high", wiki -> "medium", novel -> "medium-low", ephemera -> "low"
- Generate an embedding for each chunk using the Voyage AI API, model "voyage-context-4". Read the API key from the VOYAGE_API_KEY environment variable, never hardcode it. Use the tenacity library for exponential backoff retry (1s, 2s, 4s, 8s) on any API call, since the free tier rate-limits.
- Store everything in a local persistent Chroma collection named "archive_chunks", saved to data/chroma/
- Print a summary at the end: total documents processed, total chunks created, count per source_type, count of files that failed to parse
- Make this script safely re-runnable (don't duplicate chunks if run twice — use chunk_id as the Chroma document ID so re-inserting overwrites instead of duplicating)

Add a docstring at the top of the file explaining what it does and how to run it.
```

---

### Prompt 2 — Knowledge graph builder

```
Build src/ingestion/build_graph.py.

Goal: extract entities and relationships from the ingested chunks and build a knowledge graph, so multi-hop questions can be answered by walking connections between facts.

Requirements:
- Load all chunks and their metadata from the Chroma collection "archive_chunks" created by src/ingestion/ingest.py (data/chroma/)
- For each chunk, call an LLM (via OpenRouter, using OPENROUTER_API_KEY and OPENROUTER_MODEL environment variables) with a prompt that asks it to extract entities and relationships in the form: {"from": "...", "relation": "...", "to": "..."}. Ask for a JSON array in the response, and handle parsing failures gracefully (skip that chunk, log a warning, keep going — don't crash the whole run over one bad chunk)
- Use tenacity for exponential backoff retry on every LLM call
- Build a NetworkX MultiDiGraph: nodes are entities, edges are relationships. Each edge must carry this metadata: source_chunk_id, trust_tier (copy from the source chunk's trust_tier)
- Save the finished graph to data/graph.gpickle using networkx's pickle functions
- Print a summary: total entities (nodes), total relationships (edges), how many chunks were skipped due to parse failure
- Make this safe to re-run: if data/graph.gpickle already exists, rebuild it fresh rather than appending duplicate edges

Add a docstring explaining what it does and how to run it. This script should be runnable independently after Prompt 1's ingest.py has completed.
```

---

### Prompt 3 — Retrieval layer

```
Build src/backend/retrieval/vector_search.py and src/backend/retrieval/graph_search.py.

vector_search.py:
- Export a function: search_chunks(query: str, top_k: int = 5) -> list[dict]
- It should: embed the query using Voyage AI "voyage-context-4" (same model as ingestion, read VOYAGE_API_KEY from env), then query the Chroma collection "archive_chunks" (loaded from data/chroma/) for the top_k closest chunks
- Each returned dict must have exactly these keys: chunk_id, text, source_doc, page, source_type, trust_tier
- Use tenacity for exponential backoff on the embedding API call

graph_search.py:
- Export a function: search_graph(entities: list[str], max_hops: int = 2) -> list[dict]
- Load the graph from data/graph.gpickle (built by src/ingestion/build_graph.py)
- Starting from any node names matching the given entities (case-insensitive partial match is fine), walk up to max_hops edges out
- Return a list of dicts, one per edge found, each with: from, relation, to, source_chunk_id, trust_tier

Both functions must have clear docstrings and type hints. Do not call any LLM in graph_search.py — it's pure graph traversal, no API cost.
```

---

### Prompt 4 — Trust & contradiction layer

```
Build src/backend/trust.py.

Requirements:
- Export a constant TRUST_TIERS = {"codex": "high", "wiki": "medium", "novel": "medium-low", "ephemera": "low"} for reference elsewhere in the codebase
- Export a function: detect_contradictions(chunks: list[dict]) -> list[dict]
  - Input: a list of chunk dicts (same shape as returned by vector_search.search_chunks — keys: chunk_id, text, source_doc, page, source_type, trust_tier)
  - For every pair of chunks whose text seems to be about the same topic or fact, call an LLM (via OpenRouter, OPENROUTER_API_KEY + OPENROUTER_MODEL from env) with a short prompt asking: "Do these two passages agree, or do they conflict on a specific fact? Answer in JSON: {\"conflict\": true/false, \"topic\": \"...\"}"
  - Only compare pairs, don't do an expensive all-pairs check if there are many chunks — cap it at checking the 5 most similar pairs by simple keyword/entity overlap first, to control API usage
  - Return a list of dicts shaped like: {"topic": "...", "sources_disagree": ["source_doc_1", "source_doc_2"]} — this must match the "contradictions" field shape in the API contract in docs/architecture.md section 6
  - Use tenacity for exponential backoff on the LLM call

Add docstrings and type hints. This file has no FastAPI or agent logic in it — just trust tier data and the contradiction check.
```

---

### Prompt 5 — The three agents

```
Build src/backend/agents/planner.py, src/backend/agents/critic.py, and src/backend/agents/synthesizer.py.

All three call an LLM via OpenRouter (OPENROUTER_API_KEY + OPENROUTER_MODEL from env), using tenacity for exponential backoff retry.

planner.py:
- Export function: plan_next_search(question: str, chunks_so_far: list[dict]) -> str
- Given the original question and everything retrieved so far, ask the LLM to output either a new, more specific search query (as a plain string) to run next, or the literal string "DONE" if it believes enough has been gathered to answer
- Keep the prompt to the LLM simple and explicit about this choice

critic.py:
- Export function: evaluate_evidence(question: str, chunks_so_far: list[dict]) -> dict
- Call src/backend/trust.py's detect_contradictions() on chunks_so_far
- Ask the LLM whether the gathered chunks are enough to fully answer the question
- Return a dict shaped exactly like: {"enough": true/false, "contradictions": [...]} where contradictions is whatever detect_contradictions() returned (can be an empty list)

synthesizer.py:
- Export function: write_answer(question: str, chunks: list[dict], contradictions: list[dict]) -> dict
- Ask the LLM to write a final answer to the question using only the given chunks as evidence — instruct it clearly not to use outside/general knowledge, since this is a fictional corpus and the answer must come only from provided chunks
- If contradictions is non-empty, the answer text must explicitly mention the disagreement rather than silently picking one side
- Return a dict shaped exactly like: {"answer": "...", "sources": [{"title": source_doc + optional page, "trust": trust_tier, "snippet": short excerpt of chunk text} for each chunk used]}
- This output shape must slot directly into the final API response defined in docs/architecture.md section 6

Add docstrings and type hints to all three files. Each file should only do its one job — do not merge these into one file.
```

---

### Prompt 6 — Orchestrator (the agent loop)

```
Build src/backend/orchestrator.py.

Goal: tie planner, critic, synthesizer, and retrieval together into the search loop described in docs/architecture.md section 3.

Requirements:
- Export function: run_archivist(question: str) -> dict
- Hard limit: maximum 5 search hops (loop iterations). This must be enforced with a simple counter — never allow an unbounded loop.
- Loop logic per hop:
  1. Call planner.plan_next_search(question, chunks_so_far) to get the next search query, or "DONE"
  2. If "DONE", break out of the loop
  3. Otherwise, call retrieval.vector_search.search_chunks(query) and retrieval.graph_search.search_graph(...) as relevant, add results to chunks_so_far (avoid duplicate chunk_ids)
  4. Call critic.evaluate_evidence(question, chunks_so_far)
  5. Record a reasoning step for this hop: {"step": hop_number, "action": f"Searched: '{query}'", "found": f"{len(new_chunks)} relevant chunks"}
  6. If critic says enough=true, break out of the loop
- After the loop ends (either by "DONE", critic satisfaction, or hitting the 5-hop cap), call synthesizer.write_answer(question, chunks_so_far, contradictions) to get the final answer
- If the loop ended because of the 5-hop cap without the critic being satisfied, still produce an answer but make sure the synthesizer is told to note the uncertainty honestly in the answer text
- Assemble and return the final dict matching the exact API contract in docs/architecture.md section 6: keys "answer", "reasoning_steps", "sources", "contradictions"

Add a clear docstring and type hints. This file should read like a simple loop, not a framework — no external agent libraries.
```

---

### Prompt 7 — FastAPI backend

```
Build src/backend/main.py.

Requirements:
- FastAPI app with two endpoints:
  - POST /api/ask — request body: {"question": "string"}. Calls orchestrator.run_archivist(question) and returns its result directly. Response must match the exact shape in docs/architecture.md section 6.
  - GET /api/health — returns {"status": "ok"}
- Load environment variables from .env using python-dotenv at startup
- Enable CORS for all origins (this is a hackathon demo, keep it simple) so the React frontend can call it from a different port during development
- Wrap the /api/ask logic in a try/except that returns a clear JSON error message with HTTP 500 if anything fails, instead of crashing — a demo crash is worse than a graceful error
- Add a docstring at the top of the file and a comment showing the command to run it (uvicorn src.backend.main:app --reload)

Do not add authentication or rate limiting — not needed for this hackathon demo.
```

---

### Prompt 8 — Next.js frontend (connect to real API)

```
Build the frontend in src/frontend/ using Next.js (App Router) and Tailwind CSS.

Layout: a three-panel split-screen layout.
- Left panel ("Sources"): shows the source documents used for the current answer, each as a card with title, snippet, and a colored trust badge (green = "high", yellow = "medium", orange = "medium-low", red = "low")
- Center panel ("Chat"): question input at the bottom, scrolling list of question/answer pairs above it. When a response's contradictions array is non-empty, show an amber banner above that answer listing the topic and which sources disagree
- Right panel ("Reasoning Trace"): shows the agent's search steps for the current question, in order (step number, action, what was found), updating as they arrive

Requirements:
- Call POST http://localhost:8000/api/ask (read the base URL from environment variable NEXT_PUBLIC_API_URL, don't hardcode it) with {"question": "..."} and render the response
- Response shape to render, matching docs/architecture.md section 6: answer, reasoning_steps, sources, contradictions
- Show a loading state while waiting for the response — the agent loop can take several seconds
- Keep components small and in separate files: ChatPanel, SourcesPanel, ReasoningTracePanel, ContradictionBanner, AnswerCard
- Use "use client" for interactive components; do not create any Next.js API routes — all data comes from the FastAPI backend only
- Use Tailwind utility classes only, no additional CSS framework
- Single screen, no additional routing/pages needed
```

---

### Prompt 9 — Telegram bot

```
Build src/bot/telegram_bot.py.

Requirements:
- Use python-telegram-bot with long-polling (no public webhook URL needed)
- Read the bot token from the TELEGRAM_BOT_TOKEN environment variable
- On any text message from a user, treat it as a question: call the local backend's POST http://localhost:8000/api/ask with {"question": message_text}
- Format the reply as plain text: the answer, followed by a short "Sources:" section listing up to 3 source titles with their trust tier in brackets, e.g. "Codex Vol. 2, p.114 [high]"
- If contradictions is non-empty, prepend a line like "⚠️ Note: sources disagree on: <topic>" before the answer
- Handle request failures gracefully — if the backend call fails or times out, reply with a plain "Something went wrong, try again" message instead of crashing the bot
- Add a docstring explaining how to run it and that the FastAPI backend (Prompt 7) must already be running locally
```

---

### Prompt 10 — Eval harness

```
Build src/eval/run_eval.py.

Requirements:
- Take the path to sample_questions.json as a CLI argument (--questions-path), don't hardcode it
- For each question in the file, call POST http://localhost:8000/api/ask and record: the question, the answer received, how many reasoning steps it took, whether any contradictions were flagged, and how long the request took in seconds
- Write all results to results/eval_log.json as a JSON array
- Print a short summary at the end: total questions run, average number of reasoning steps, average response time, count of questions where a contradiction was flagged
- This script does not judge correctness automatically (that requires manual review or a separate LLM-judge step) — it just runs everything and logs it cleanly so the team can review answers by hand

Add a docstring explaining how to run it, and note in a comment that this should be run again after any meaningful backend change to track whether things are improving or regressing.
```
