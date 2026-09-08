# Hermes backend

FastAPI service for Hermes by TheKade. Design notes are in
[docs/architecture.md](../../docs/architecture.md); the endpoint reference is in
[docs/api.md](../../docs/api.md).

## Modules

| Path | Responsibility |
|---|---|
| `main.py` | Application factory, CORS, rate limit middleware, `/assets` mount, health |
| `core/` | Settings, async PostgreSQL engine, Redis client, rate limiter, structured logging, domain exceptions |
| `ingestion/` | Document parsing with Docling and a PyMuPDF fallback, figure and table cropping, semantic chunking, Voyage embedding |
| `retrieval/` | pgvector HNSW search, full-text search, SQL Reciprocal Rank Fusion, cross-encoder reranking, search endpoints |
| `agents/` | LangGraph pipeline: nodes, graph definition with a PostgreSQL checkpointer, prompts, SSE service, session persistence |
| `workers/` | Offline CLIs: `run_ingest.py` for corpus ingestion, `run_query.py` for one-off queries with embedding visibility |

## Running

```bash
make backend                  # uvicorn with reload on port 8000
make ingest                   # offline ingestion
make ask Q="your question"    # single query from the CLI
```

Swagger UI is at `http://localhost:8000/docs`.
