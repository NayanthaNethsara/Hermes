"""Build a knowledge graph from the chunks ingested by src/ingestion/ingest.py.

What it does:
    Loads every chunk from the Chroma collection "archive_chunks"
    (data/chroma/, created by ingest.py), asks an LLM to pull entities and
    relationships out of each chunk's text, and assembles them into a
    NetworkX MultiDiGraph — nodes are entities, edges are relationships,
    and every edge carries the source chunk id and that chunk's trust
    tier. The finished graph is pickled to data/graph.gpickle.

    NOTE: networkx.write_gpickle/read_gpickle were removed in NetworkX 3.x
    (the version this project uses). We pickle the graph directly with
    Python's stdlib pickle module instead — that's exactly what those
    removed helpers did internally, so the result is equivalent.

How to run it:
    1. Run ingest.py first — this script reads what it wrote to Chroma.
    2. Copy configuration-example/.env.example to .env at the repo root
       and fill in OPENROUTER_API_KEY (OPENROUTER_BASE_URL and
       OPENROUTER_MODEL already have sensible free-tier defaults).
    3. From the repo root:
           python -m src.ingestion.build_graph
           (or: python src/ingestion/build_graph.py)

Safe to re-run: always builds a fresh graph in memory and overwrites
data/graph.gpickle, rather than loading and appending to the old one —
so re-running never produces duplicate edges.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import requests
from dotenv import load_dotenv
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
CHROMA_DIR = REPO_ROOT / "data" / "chroma"
GRAPH_PATH = REPO_ROOT / "data" / "graph.gpickle"
COLLECTION_NAME = "archive_chunks"

CHROMA_PAGE_SIZE = 200

# Minimum gap enforced between successive OpenRouter requests (this script
# calls the LLM once per chunk, back-to-back, which can trip a low
# requests-per-minute limit the same way ingestion's embedding calls did -
# see src/ingestion/ingest.py's identical VOYAGE_REQUEST_INTERVAL_SECONDS).
# Raise via .env if you still see 429s, lower if it's slower than it needs
# to be.
OPENROUTER_REQUEST_INTERVAL_SECONDS = float(
    os.environ.get("OPENROUTER_REQUEST_INTERVAL_SECONDS", "2")
)

EXTRACTION_SYSTEM_PROMPT = (
    "You are an information-extraction assistant. Read the passage and "
    "extract the entities and relationships it states. Respond with ONLY "
    "a JSON array (no prose, no markdown fences). Each item must look "
    'like: {"from": "entity name", "relation": "short relation phrase", '
    '"to": "entity name"}. If the passage has no clear entities or '
    "relationships, respond with an empty array: []"
)


@dataclass
class GraphBuildStats:
    chunks_processed: int = 0
    chunks_skipped: int = 0
    edges_added: int = 0
    skipped_chunk_ids: list[str] = field(default_factory=list)


def require_openrouter_config() -> tuple[str, str, str]:
    """Fetch OpenRouter config or fail fast with a clear message.

    Checked once up front (not inside the retried API-call function) so a
    missing key fails immediately instead of being retried five times by
    tenacity and surfacing as an opaque RetryError.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.environ.get("OPENROUTER_MODEL")
    if not api_key or not model:
        raise RuntimeError(
            "OPENROUTER_API_KEY and OPENROUTER_MODEL must be set - copy "
            "configuration-example/.env.example to .env at the repo root "
            "and fill them in"
        )
    return api_key, base_url, model


def _is_retryable_api_error(exc: BaseException) -> bool:
    """True for transient errors worth retrying (network hiccup, timeout,
    429 rate-limit, 5xx) - False for a 4xx client error (bad model name,
    malformed request, bad auth), which is deterministic and will fail
    identically on every retry."""
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))


_last_openrouter_request_at = 0.0


def _throttle_openrouter() -> None:
    """Sleep just long enough to keep at least
    OPENROUTER_REQUEST_INTERVAL_SECONDS between successive OpenRouter
    requests - see ingest.py's _throttle_voyage() for why backoff alone
    isn't enough against a low requests-per-minute ceiling."""
    global _last_openrouter_request_at
    elapsed = time.monotonic() - _last_openrouter_request_at
    remaining = OPENROUTER_REQUEST_INTERVAL_SECONDS - elapsed
    if remaining > 0:
        time.sleep(remaining)
    _last_openrouter_request_at = time.monotonic()


@retry(
    retry=retry_if_exception(_is_retryable_api_error),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(6),
)
def call_llm(chunk_text: str) -> str:
    """Ask the configured OpenRouter model to extract entities/relationships
    from a chunk of text. Retries with exponential backoff (2s, 4s, 8s,
    16s, 30s - ~60s total) on transient errors since the free tier
    rate-limits - not on a 4xx client error, which would never succeed no
    matter how many retries. Returns the raw response content."""
    api_key, base_url, model = require_openrouter_config()

    _throttle_openrouter()
    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": chunk_text},
            ],
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def parse_relations(raw_content: str) -> list[dict] | None:
    """Parse the LLM's response into a list of {from, relation, to} dicts.

    Returns None (rather than raising) if the response isn't valid JSON,
    so the caller can skip the chunk and keep going instead of crashing
    the whole run over one bad response.
    """
    candidate = raw_content.strip()

    # Strip a ```json ... ``` or ``` ... ``` fence if the model added one
    # despite being asked not to.
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1).strip()

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        # Last resort: grab the first [...] block in case of stray prose.
        bracket_match = re.search(r"\[.*\]", candidate, re.DOTALL)
        if not bracket_match:
            return None
        try:
            parsed = json.loads(bracket_match.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(parsed, list):
        return None

    relations = [
        item
        for item in parsed
        if isinstance(item, dict) and {"from", "relation", "to"} <= item.keys()
    ]
    return relations


# Highest trust first. OpenRouter's free tier is 50 requests/day with no
# purchase history (confirmed from their docs), one call per chunk - a
# corpus of several thousand chunks doesn't fit in a demo timeline without
# either paying or running across many days (see docs/decisions.md "graph
# build scope"). When --max-chunks caps the run, this ordering means the
# graph gets built from the most reliable, best-structured content first
# (codex-tier text tends to be dense registry/record-style writing, which
# extracts cleanly into entities and relationships) rather than an
# arbitrary slice.
TRUST_TIER_PRIORITY = {"high": 0, "medium": 1, "medium-low": 2, "low": 3}


def fetch_all_chunks(max_chunks: int | None = None) -> list[dict]:
    """Page through the archive_chunks collection and return chunks as
    {chunk_id, text, trust_tier}.

    If max_chunks is given and the collection has more than that, returns
    the max_chunks highest-trust-tier chunks (see TRUST_TIER_PRIORITY)
    rather than an arbitrary prefix.
    """
    client = _chroma_client()
    collection = client.get_collection(COLLECTION_NAME)

    chunks = []
    offset = 0
    while True:
        page = collection.get(
            limit=CHROMA_PAGE_SIZE, offset=offset, include=["documents", "metadatas"]
        )
        ids = page["ids"]
        if not ids:
            break
        for chunk_id, text, metadata in zip(ids, page["documents"], page["metadatas"]):
            chunks.append(
                {"chunk_id": chunk_id, "text": text, "trust_tier": metadata["trust_tier"]}
            )
        offset += len(ids)

    if max_chunks is not None and len(chunks) > max_chunks:
        chunks.sort(key=lambda c: TRUST_TIER_PRIORITY.get(c["trust_tier"], 99))
        chunks = chunks[:max_chunks]

    return chunks


def _chroma_client():
    import chromadb

    if not CHROMA_DIR.exists():
        raise RuntimeError(
            f"{CHROMA_DIR} does not exist - run ingest.py first "
            "(see src/ingestion/ingest.py)"
        )
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def build_graph(chunks: list[dict], stats: GraphBuildStats) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()

    for chunk in chunks:
        try:
            raw_content = call_llm(chunk["text"])
            relations = parse_relations(raw_content)
        except Exception as exc:  # noqa: BLE001 - one bad chunk must not stop the run
            print(f"WARNING: skipping chunk {chunk['chunk_id']}: {exc}")
            stats.chunks_skipped += 1
            stats.skipped_chunk_ids.append(chunk["chunk_id"])
            continue

        if relations is None:
            print(
                f"WARNING: skipping chunk {chunk['chunk_id']}: "
                "could not parse a JSON array from the LLM response"
            )
            stats.chunks_skipped += 1
            stats.skipped_chunk_ids.append(chunk["chunk_id"])
            continue

        for relation in relations:
            graph.add_edge(
                relation["from"],
                relation["to"],
                relation=relation["relation"],
                source_chunk_id=chunk["chunk_id"],
                trust_tier=chunk["trust_tier"],
            )
            stats.edges_added += 1

        stats.chunks_processed += 1

    return graph


def save_graph(graph: nx.MultiDiGraph) -> None:
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GRAPH_PATH, "wb") as f:
        pickle.dump(graph, f)


def print_summary(graph: nx.MultiDiGraph, stats: GraphBuildStats) -> None:
    print("\n--- Graph build summary ---")
    print(f"Total entities (nodes):      {graph.number_of_nodes()}")
    print(f"Total relationships (edges): {graph.number_of_edges()}")
    print(f"Chunks processed:            {stats.chunks_processed}")
    print(f"Chunks skipped (parse failure or error): {stats.chunks_skipped}")
    for chunk_id in stats.skipped_chunk_ids:
        print(f"  - {chunk_id}")


def main() -> None:
    # Chunk text echoed in warnings can contain non-ASCII characters; on a
    # Windows console (cp1252) printing those raises UnicodeEncodeError
    # and would kill a long graph build. Degrade to "?" instead.
    sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Cap the number of chunks sent to the LLM, highest-trust-tier "
        "first (see TRUST_TIER_PRIORITY). Default: no cap, use every "
        "chunk - only advisable with a paid OpenRouter balance; the free "
        "tier is 50 requests/day.",
    )
    args = parser.parse_args()

    try:
        require_openrouter_config()
        chunks = fetch_all_chunks(max_chunks=args.max_chunks)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None

    if not chunks:
        raise SystemExit(
            "No chunks found in the archive_chunks collection - run ingest.py first"
        )

    stats = GraphBuildStats()
    graph = build_graph(chunks, stats)
    save_graph(graph)
    print_summary(graph, stats)


if __name__ == "__main__":
    main()
