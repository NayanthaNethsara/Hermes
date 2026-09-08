# API Reference

Base URL in development: `http://localhost:8000`. All request and response
bodies are JSON unless stated otherwise.

The service publishes its own OpenAPI schema, so the endpoint list below is
also browsable and callable while the backend is running:

| Page | URL |
|---|---|
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| OpenAPI schema | http://localhost:8000/openapi.json |

Swagger covers the request and response models. It cannot exercise the two
streaming endpoints, so their event contract is documented here instead.

## Ask

### POST /api/ask/stream

Primary endpoint. Streams the answer as Server-Sent Events.

Request:

```json
{
  "question": "In the portrait of Ignatz Ashgrove, what object are they holding?",
  "session_id": "b1f0c2de-1f3c-4a6f-9c11-6f0d7d2a9e42",
  "max_iterations": 5
}
```

`session_id` defaults to `"default"` and `max_iterations` to 5 (1 to 10).
Passing a stable `session_id` is what gives follow-up questions their history.

Events arrive in this order:

| Event | Payload | Notes |
|---|---|---|
| `status` | `{stage, message}` | One per node: `starting`, `guardrail`, `planning`, `retrieving`, `arbitrating`, `synthesizing` |
| `metadata` | `{sources, referenced_figures, citations, reasoning_steps}` | Emitted after retrieval, before any answer text |
| `metadata` | `{..., contradictions}` | Emitted again after arbitration |
| `token` | `{delta}` | Repeated for each generated fragment |
| `done` | Full response object | Final state, same shape as `POST /api/ask` |
| `error` | `{error}` | Terminates the stream |

```
event: status
data: {"stage": "retrieving", "message": "Searching archive with hybrid vector search..."}

event: token
data: {"delta": "According to "}

event: done
data: {"answer": "...", "sources": [...], "reasoning_steps": [...], "contradictions": []}
```

### POST /api/ask

Same request body, no streaming. Returns the complete response once the graph
finishes.

```json
{
  "answer": "string",
  "referenced_figures": ["plates/codex_vol2_plate7.png"],
  "citations": ["codex_vol2"],
  "sources": [
    {
      "chunk_id": "codex_vol2_p114_c3",
      "title": "codex_vol2",
      "section": "Chapter 4",
      "category": "codex",
      "epistemic_weight": 1.0,
      "vector_score": 0.8123,
      "keyword_score": 0.4410,
      "relevance_score": 0.9102,
      "figures": [],
      "trust": "high",
      "snippet": "..."
    }
  ],
  "reasoning_steps": [
    {"step": 1, "action": "Input Guardrail & Intent Classification", "found": "..."},
    {"step": 2, "action": "Contextual Query Planning", "found": "..."},
    {"step": 3, "action": "Hybrid Archive Retrieval", "found": "..."},
    {"step": 4, "action": "Epistemic Source Arbitration", "found": "..."},
    {"step": 5, "action": "Evidence Synthesis", "found": "..."}
  ],
  "contradictions": [
    {"topic": "Forging year of the artifact", "sources_disagree": ["codex_vol2", "ballad_7"]}
  ]
}
```

`POST /agents/run` and `POST /agents/stream` are equivalent endpoints that take
`query` instead of `question`.

## Sessions

| Method | Path | Description |
|---|---|---|
| GET | `/api/sessions` | List sessions, newest first: `id`, `title`, `updated_at`, `turn_count` |
| GET | `/api/sessions/{session_id}` | One session: `id`, `title`, `summary`, `turns`, `created_at`, `updated_at`. 404 if unknown |
| DELETE | `/api/sessions/{session_id}` | Delete a session. Returns `{"ok": true}`, 404 if unknown |

A 404 from the detail endpoint is normal for a session id that has not received
its first question yet; the frontend treats it as an empty conversation.

## Documents and visuals

| Method | Path | Description |
|---|---|---|
| GET | `/api/documents/{doc_id}` | Document metadata plus every chunk in order |
| GET | `/api/visuals/{filename}` | Catalog entry for one extracted visual asset |
| GET | `/assets/{path}` | The extracted asset files themselves, served statically |

## Retrieval

### POST /retrieval/search

Runs retrieval on its own, without the agent graph. Useful for debugging
recall and ranking.

```json
{
  "query": "garrison strength of Greyfell Citadel",
  "top_k": 50,
  "rerank_top_k": 5,
  "min_score": 0.5,
  "filter_category": null
}
```

Returns `{results, referenced_figures}`, where each result is a chunk with its
vector, keyword and rerank scores.

## Health

### GET /api/health

```json
{"status": "ok", "service": "hermes-backend", "redis": "connected"}
```

`redis` is `unavailable` when the cache is down. That is not a failure state;
caching and rate limiting fail open.

## Errors

Domain errors return a consistent body:

```json
{"error_type": "RetrievalThresholdError", "message": "...", "path": "/api/ask"}
```

| Status | Meaning |
|---|---|
| 404 | Session, document or asset not found, or retrieval confidence below threshold |
| 422 | Invalid request body, or document parsing failure during ingestion |
| 429 | Rate limit exceeded, see `REDIS_RATE_LIMIT_REQUESTS` |
| 502 | Language or vision model call failed |

## Rate limiting

Requests are counted per client IP over a sliding window, 30 per 60 seconds by
default. Both values are configurable, see [configuration.md](configuration.md).
When Redis is unreachable the limiter allows the request through.
