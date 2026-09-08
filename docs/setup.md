# Setup

From a fresh clone to a working instance. Each step ends with a check; if a
check fails, fix it before continuing, because every later step depends on it.

## 1. Prerequisites

| Tool | Version | Used for | Check |
|---|---|---|---|
| Python | 3.11+ | Backend and workers | `python3 --version` |
| Node.js | 20+ | Frontend | `node --version` |
| Docker | recent | PostgreSQL and Redis | `docker --version` |

## 2. Credentials

Hermes needs an embedding provider and a language model provider.

**Voyage AI (required).** Create a key at https://dash.voyageai.com/ and set
`VOYAGE_API_KEY`.

**Google Gemini (required, two options).**

- Vertex AI: create or select a GCP project with the Vertex AI API enabled, run
  `gcloud auth application-default login`, then set `GCP_PROJECT_ID` and
  `GCP_LOCATION`.
- Direct API key: create one at https://aistudio.google.com/apikey and set
  `GEMINI_API_KEY`.

`OPENROUTER_API_KEY` is an optional fallback used only when neither Gemini path
is configured.

## 3. Environment file

```bash
cp configuration-example/.env.example .env
```

Fill in the blanks. Every service reads this one file at the repository root.
The full variable reference is in [configuration.md](configuration.md).

**Check:** `git status` does not list `.env`. It is gitignored and must stay
that way.

## 4. Infrastructure

```bash
make db
```

This starts PostgreSQL with pgvector and Redis via Docker Compose.

**Check:** `docker ps` shows both containers healthy.

## 5. Dependencies

```bash
make setup
```

The backend installs with `uv` when available and falls back to a virtualenv at
`src/backend/.venv`. The frontend installs with npm.

**Check:** `python3 -c "import fastapi, langgraph, asyncpg"` exits without
error.

## 6. Ingest the corpus

Place the source documents under `data/raw_archive` (or point
`RAW_ARCHIVE_DIR` elsewhere), then:

```bash
make ingest
```

This is a one-time offline step. It parses each document, extracts figures into
`data/extracted_assets`, chunks and embeds the text, and writes to PostgreSQL.
Re-running skips files that are already ingested; pass `--force` to reprocess.

**Check:** the run reports a non-zero chunk total and `document_chunks` has
rows.

## 7. Run the backend

```bash
make backend
```

**Check:**

```bash
curl http://localhost:8000/api/health
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Who is Gareth Ironmere?"}'
```

The health endpoint returns `status: ok`; the ask endpoint returns `answer`,
`sources`, `reasoning_steps` and `contradictions`.

## 8. Run the frontend

In a second terminal:

```bash
make frontend
```

Open http://localhost:3000/chat.

**Check:** a question streams in token by token, source cards with trust badges
appear before the text, and the reasoning trace fills in.

## 9. Docker

To run everything in containers instead:

```bash
make docker-up
```

Backend on port 8000, frontend on port 3000. Ingestion still runs on the host
against the same database.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Answers say configuration is required | No model provider configured. Set `GCP_PROJECT_ID` or `GEMINI_API_KEY` in `.env` |
| `connection refused` on port 5432 | PostgreSQL is not running. `make db` |
| Redis warning in the logs | Redis is optional and fails open. `make redis` to enable caching and rate limiting |
| Frontend cannot reach the backend | Backend is down, or `NEXT_PUBLIC_API_URL` points somewhere else |
| Embedding request returns HTTP 400 | `VOYAGE_MODEL` is not a valid model name, check https://docs.voyageai.com/docs/embeddings |
| 429 responses | Rate limit reached, 30 requests per minute per IP by default. Wait or raise `REDIS_RATE_LIMIT_REQUESTS` |
| Retrieval returns nothing | The corpus is not ingested, or `RERANK_SCORE_THRESHOLD` is too high |
| `/chat/<id>` loads empty | Expected for a session id with no turns yet |
