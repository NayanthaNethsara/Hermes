# Environment Configuration Guide

This directory contains template configuration files and setup guidelines for The Archivist.

## Single Root Environment File

All backend modules, offline workers, CLI scripts, and Docker Compose services load their configuration from a single `.env` file located at the **repository root**:

```
Archivist/
├── .env                  <-- Place active configuration file here
├── configuration-example/
│   ├── .env.example      <-- Template reference
│   └── README.md
├── src/
│   ├── backend/
│   └── frontend/
```

### Initial Setup

Copy the example file to `.env` at the repository root:

```bash
cp configuration-example/.env.example .env
```

Edit `.env` to supply required API keys and credentials.

---

## Configuration Reference

### 1. Database (PostgreSQL + pgvector)

- `DATABASE_URL`: SQLAlchemy connection string with the `postgresql+asyncpg` driver.
- When running PostgreSQL locally via Docker Compose (`make db`), use:
  ```env
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/archivist
  ```

### 2. Embeddings & Reranker (Voyage AI)

- `VOYAGE_API_KEY`: API key from Voyage AI.
- `VOYAGE_MODEL`: Default is `voyage-multimodal-3.5` for interleaved text and diagram embedding.
- `VOYAGE_RERANK_MODEL`: Default is `rerank-2.5` for cross-encoder reranking.

### 3. Reasoning & Vision LLM

- `GCP_PROJECT_ID`: Google Cloud project identifier for Vertex AI.
- `GCP_LOCATION`: Vertex AI region (e.g. `us-central1`).
- `GEMINI_MODEL`: Default is `gemini-1.5-pro`.
- `GEMINI_API_KEY`: (Optional) Direct Google AI Studio API key if not using GCP Service Account.
- `OPENROUTER_API_KEY`: (Optional) Fallback LLM provider if Vertex AI credentials are not supplied.

### 4. Data Directories

- `RAW_ARCHIVE_DIR`: Directory containing raw input documents (`data/raw_archive`).
- `ASSETS_DIR`: Output directory where extracted and cropped figure/table images are saved and served (`data/extracted_assets`).

### 5. Search Thresholds

- `RERANK_SCORE_THRESHOLD`: Minimum relevance score (default: `0.50`) required for candidates to be admitted into synthesis context.
- `RETRIEVAL_CANDIDATE_LIMIT`: Maximum preliminary candidates retrieved from SQL RRF (default: `50`).
- `RERANK_TOP_K`: Number of high-confidence chunks passed to the synthesizer (default: `5`).
- `MAX_SEARCH_HOPS`: Maximum iterations for the Track 1C multi-hop investigator state machine (default: `5`).

---

## Frontend Configuration

The Next.js frontend has a separate local environment file at `src/frontend/.env.local`:

```bash
cp src/frontend/.env.local.example src/frontend/.env.local
```

Configured variable:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```
