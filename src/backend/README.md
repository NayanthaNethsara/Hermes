# Archivist Backend

Domain-based modular backend for The Archivist multimodal AI research assistant.

## Architecture & Modules

- **`core/`**: Infrastructure, configuration (`Settings`), async PostgreSQL + pgvector session management, structured logging, and domain exception handlers.
- **`ingestion/`**: Spatial document layout parser (IBM Docling with PyMuPDF fallback), Pillow figure/table cropper, semantic chunker, and Voyage AI multimodal embedder.
- **`retrieval/`**: PostgreSQL `pgvector` HNSW index, full-text `TSVECTOR` search, SQL Reciprocal Rank Fusion (RRF), Voyage `rerank-2.5` cross-encoder, and FastAPI `/retrieval/search` router.
- **`agents/`**: LangGraph state machine workflows:
  - `nodes/`: Modular steps (`planner`, `retriever`, `evaluator`, `visualizer`, `synthesizer`).
  - `graphs/`: Sub-track 1A linear DAG (`multimodal_1a`) and Sub-track 1C iterative graph (`investigator_1c`).
  - `router.py`: Endpoints for `POST /agents/run/{track_id}` and `POST /api/ask`.
- **`workers/`**: Standalone CLI offline ingestion worker (`run_ingest.py`).
- **`main.py`**: FastAPI application entry point, mounting `/assets` and registering routers.
