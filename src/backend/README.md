# Archivist Backend

Domain-based modular backend for The Archivist multimodal AI research assistant.

## Architecture & Modules

- **`core/`**: Infrastructure, configuration (`Settings`), async PostgreSQL + pgvector session management, structured logging, and domain exception handlers.
- **`ingestion/`**: Spatial document layout parser (IBM Docling with PyMuPDF fallback), Pillow figure/table cropper, semantic chunker, and Voyage AI multimodal embedder.
- **`retrieval/`**: PostgreSQL `pgvector` HNSW index, full-text `TSVECTOR` search, SQL Reciprocal Rank Fusion (RRF), Voyage `rerank-2.5` cross-encoder, and FastAPI `/retrieval/search` router.
- **`agents/`**: LangGraph unified state machine workflow:
  - `nodes/`: Modular steps (`rewriter`, `retriever`, `arbitrator`, `synthesizer`).
  - `graphs/`: Unified conversational graph (`workflow.py`) with PostgreSQL session checkpointer.
  - `router.py`: Endpoints for `POST /api/ask`, `POST /api/ask/stream`, `POST /agents/run`, and `POST /agents/stream`.
- **`workers/`**: Standalone CLI offline ingestion worker (`run_ingest.py`).
- **`main.py`**: FastAPI application entry point, mounting `/assets` and registering routers.
