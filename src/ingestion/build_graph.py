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

import json
import os
import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import requests
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
CHROMA_DIR = REPO_ROOT / "data" / "chroma"
GRAPH_PATH = REPO_ROOT / "data" / "graph.gpickle"
COLLECTION_NAME = "archive_chunks"

CHROMA_PAGE_SIZE = 200

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


@retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(5))
def call_llm(chunk_text: str) -> str:
    """Ask the configured OpenRouter model to extract entities/relationships
    from a chunk of text. Retries with exponential backoff (1s, 2s, 4s, 8s)
    since the free tier rate-limits. Returns the raw response content."""
    api_key, base_url, model = require_openrouter_config()

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


def fetch_all_chunks() -> list[dict]:
    """Page through the archive_chunks collection and return every chunk
    as {chunk_id, text, trust_tier}."""
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
    try:
        require_openrouter_config()
        chunks = fetch_all_chunks()
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
