# Configuration

All backend modules, the offline workers and Docker Compose read one `.env`
file at the repository root. `configuration-example/.env.example` is the
template; copy it and fill in the blanks:

```bash
cp configuration-example/.env.example .env
```

`.env` is gitignored and must stay that way. Settings are loaded and validated
in `src/backend/core/config.py`; anything not set falls back to the default
below.

## Database

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/archivist` | PostgreSQL connection string. Must use the `postgresql+asyncpg` driver |

The same database holds the chunk table, the chat sessions and the LangGraph
checkpoints. Docker Compose provisions it with the pgvector image.

## Redis

| Variable | Default | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Cache and rate limit store |
| `REDIS_RATE_LIMIT_REQUESTS` | `30` | Requests allowed per window, per IP |
| `REDIS_RATE_LIMIT_WINDOW_SECONDS` | `60` | Length of the sliding window |
| `REDIS_CACHE_TTL_SECONDS` | `3600` | Lifetime of cached retrieval results |

Redis is optional. When it is unreachable the cache is bypassed and the rate
limiter allows requests through.

## Embeddings and reranking

| Variable | Default | Purpose |
|---|---|---|
| `VOYAGE_API_KEY` | empty | Required. Voyage AI credential |
| `VOYAGE_MODEL` | `voyage-multimodal-3.5` | Embedding model for documents and queries |
| `VOYAGE_RERANK_MODEL` | `rerank-2.5` | Cross-encoder used to rerank candidates |

## Language model

Gemini is used when `GCP_PROJECT_ID` or a Gemini API key is present. OpenRouter
is the fallback when neither is. With no provider at all the service starts and
answers with a message saying configuration is required.

| Variable | Default | Purpose |
|---|---|---|
| `GCP_PROJECT_ID` | empty | Vertex AI project. Pair with application default credentials |
| `GCP_LOCATION` | `global` | Vertex AI region |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model used by the planner, arbitrator and synthesizer |
| `GEMINI_API_KEY` | unset | Google AI Studio key, an alternative to the GCP project |
| `OPENROUTER_API_KEY` | empty | Optional fallback provider |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Fallback endpoint |
| `OPENROUTER_MODEL` | `google/gemini-2.0-flash-exp:free` | Fallback model |

## Storage

| Variable | Default | Purpose |
|---|---|---|
| `RAW_ARCHIVE_DIR` | `data/raw_archive` | Source documents read by the ingestion worker |
| `ASSETS_DIR` | `data/extracted_assets` | Extracted figures and tables, served at `/assets` |

Paths are resolved relative to the repository root.

## Retrieval tuning

| Variable | Default | Purpose |
|---|---|---|
| `RETRIEVAL_CANDIDATE_LIMIT` | `50` | Candidates pulled from hybrid RRF search |
| `RERANK_SCORE_THRESHOLD` | `0.50` | Minimum rerank score to stay in the running |
| `RERANK_TOP_K` | `5` | Chunks kept per search query |
| `SYNTHESIS_CONTEXT_LIMIT` | `10` | Upper bound on passages handed to the synthesizer, across all hops |
| `MAX_SEARCH_HOPS` | `2` | Search hops per question, and the main lever on the model call budget |

Raising `RERANK_SCORE_THRESHOLD` trades recall for precision; if answers start
reporting no evidence, lower it before anything else.

`MAX_SEARCH_HOPS` costs one extra model call per hop beyond the first: 2 hops
is at most 5 calls per question, 3 hops at most 6. On a free-tier quota, set it
against the per-minute limit rather than as high as it will go. The per-request
`max_iterations` is clamped to this value, so a client cannot exceed it.

`SYNTHESIS_CONTEXT_LIMIT` bounds tokens rather than calls. Each hop can add up
to `RERANK_TOP_K` passages per search query, so a multi-hop question would
otherwise grow the answer prompt without limit. When the gathered evidence
exceeds this number it is reranked once against the original question and
trimmed. That rerank is a Voyage call, not a language model call, so it does
not count against the model budget.

## Source authority weights

These set the epistemic weight attached to each source category at ingestion
and drive the arbitrator's ordering. See
[architecture.md](architecture.md#4-source-authority).

| Variable | Default |
|---|---|
| `WEIGHT_CODEX` | `1.0` |
| `WEIGHT_IMAGE` | `1.0` |
| `WEIGHT_WIKI` | `0.8` |
| `WEIGHT_NOVEL` | `0.6` |
| `WEIGHT_EPHEMERA` | `0.4` |

An unrecognized category falls back to `0.5`.

## Frontend

The frontend has its own file at `src/frontend/.env.local`:

```bash
cp src/frontend/.env.local.example src/frontend/.env.local
```


| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend base URL used by the browser |

Because it is a `NEXT_PUBLIC_` variable it is inlined at build time. In Docker
it is passed as a build argument, not just at runtime.
