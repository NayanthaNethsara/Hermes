"""Vector search over the ingested archive chunks (Chroma).

Exports search_chunks(query, top_k), which embeds a query with Voyage AI
and returns the top_k closest chunks from the "archive_chunks" Chroma
collection (data/chroma/, created by src/ingestion/ingest.py).

Run src/ingestion/ingest.py first — this module only reads what it wrote.
"""

from __future__ import annotations

import os
from pathlib import Path

import chromadb
import requests
from dotenv import load_dotenv
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

REPO_ROOT = Path(__file__).resolve().parents[3]

# Pinned to the repo root - a bare load_dotenv() searches upward from this
# file and can pick up a stray .env inside src/ instead. See src/backend/llm.py.
load_dotenv(REPO_ROOT / ".env")

CHROMA_DIR = REPO_ROOT / "data" / "chroma"
COLLECTION_NAME = "archive_chunks"

# Overridable via .env - but this MUST stay the same model that
# src/ingestion/ingest.py used, or query embeddings land in a different
# vector space than the stored chunks and results become meaningless.
# If you change VOYAGE_MODEL, re-run ingestion.
VOYAGE_API_URL = os.environ.get(
    "VOYAGE_API_URL", "https://api.voyageai.com/v1/embeddings"
)
VOYAGE_MODEL = os.environ.get("VOYAGE_MODEL", "voyage-4-lite")


def require_voyage_api_key() -> str:
    """Fetch VOYAGE_API_KEY or fail fast with a clear message.

    Checked up front (not inside the retried embed_query call) so a
    missing key fails immediately instead of being retried five times by
    tenacity and surfacing as an opaque RetryError.
    """
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "VOYAGE_API_KEY is not set - copy configuration-example/.env.example "
            "to .env at the repo root and fill it in"
        )
    return api_key


def _is_retryable_api_error(exc: BaseException) -> bool:
    """True for transient errors worth retrying (network hiccup, timeout,
    429 rate-limit, 5xx) - False for a 4xx client error (bad model name,
    malformed request, bad auth), which is deterministic and will fail
    identically on every retry."""
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))


@retry(
    retry=retry_if_exception(_is_retryable_api_error),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(6),
)
def embed_query(query: str) -> list[float]:
    """Embed a single query string with Voyage AI (VOYAGE_MODEL).

    Retries with exponential backoff (2s, 4s, 8s, 16s, 30s - ~60s total) since the free tier
    rate-limits.
    """
    response = requests.post(
        VOYAGE_API_URL,
        headers={"Authorization": f"Bearer {require_voyage_api_key()}"},
        json={"input": [query], "model": VOYAGE_MODEL},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]


def _get_collection():
    if not CHROMA_DIR.exists():
        raise RuntimeError(
            f"{CHROMA_DIR} does not exist - run src/ingestion/ingest.py first"
        )
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_collection(COLLECTION_NAME)


def search_chunks(query: str, top_k: int = 5) -> list[dict]:
    """Return the top_k chunks whose embeddings are closest to `query`.

    Each returned dict has exactly these keys: chunk_id, text, source_doc,
    page, source_type, trust_tier. `page` is None when the source chunk
    has no known page (e.g. it came from a .txt/.docx/image file).
    """
    require_voyage_api_key()  # fail fast, before the retried embed_query call
    collection = _get_collection()
    embedding = embed_query(query)

    results = collection.query(
        query_embeddings=[embedding],
        n_results=top_k,
        include=["documents", "metadatas"],
    )

    return [
        _to_chunk_dict(chunk_id, text, metadata)
        for chunk_id, text, metadata in zip(
            results["ids"][0], results["documents"][0], results["metadatas"][0]
        )
    ]


def get_chunks_by_ids(chunk_ids: list[str]) -> list[dict]:
    """Fetch specific chunks by id, in the same shape as search_chunks.

    Used to resolve graph_search results (which only carry a
    source_chunk_id, not the full chunk) back into full chunk dicts with
    real text/source_doc/page for citation. Needs no embedding, so no
    Voyage API call or key is required.
    """
    if not chunk_ids:
        return []
    collection = _get_collection()
    result = collection.get(ids=list(chunk_ids), include=["documents", "metadatas"])
    return [
        _to_chunk_dict(chunk_id, text, metadata)
        for chunk_id, text, metadata in zip(
            result["ids"], result["documents"], result["metadatas"]
        )
    ]


def _to_chunk_dict(chunk_id: str, text: str, metadata: dict) -> dict:
    page = metadata["page"]
    return {
        "chunk_id": chunk_id,
        "text": text,
        "source_doc": metadata["source_doc"],
        "page": None if page == -1 else page,
        "source_type": metadata["source_type"],
        "trust_tier": metadata["trust_tier"],
    }


if __name__ == "__main__":
    import sys

    query_arg = sys.argv[1] if len(sys.argv) > 1 else "test query"
    for chunk in search_chunks(query_arg):
        print(chunk)
