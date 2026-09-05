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

LLM backend: OpenRouter by default. If GEMINI_KEY is set in .env, this
script uses Gemini (via a Vertex AI Express-Mode API key,
`x-goog-api-key` against aiplatform.googleapis.com - a different auth
shape and response format than OpenRouter's OpenAI-compatible API, so it's
a genuinely separate code path, not a base-URL swap) instead - useful for
a one-time full-corpus build that would otherwise blow through
OpenRouter's 50-requests/day free tier (see docs/decisions.md "Graph
build scope"). This only affects this script; the live agents
(planner/critic/synthesizer/trust.py) keep using OpenRouter regardless.

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
from concurrent.futures import ThreadPoolExecutor
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

# Optional Gemini (Vertex AI Express Mode) backend for this script only - see
# the module docstring. Presence of GEMINI_KEY is what selects this path.
GEMINI_API_KEY = os.environ.get("GEMINI_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_URL = (
    "https://aiplatform.googleapis.com/v1/publishers/google/models/"
    f"{GEMINI_MODEL}:generateContent"
)
# No published rate limit hit in testing (10 back-to-back calls, all 200 OK,
# ~1-2.5s latency each) - this is a light safety margin, not a measured
# ceiling like Voyage's/OpenRouter's throttles are.
GEMINI_REQUEST_INTERVAL_SECONDS = float(
    os.environ.get("GEMINI_REQUEST_INTERVAL_SECONDS", "0.3")
)
USE_GEMINI = bool(GEMINI_API_KEY)

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


def require_gemini_config() -> str:
    """Fetch GEMINI_KEY or fail fast with a clear message.

    Checked once up front, same reasoning as require_openrouter_config().
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_KEY is not set - add it to .env at the repo root")
    return GEMINI_API_KEY


_last_openrouter_request_at = 0.0
_last_gemini_request_at = 0.0


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


def _throttle_gemini() -> None:
    """Same idea as _throttle_openrouter(), for the Gemini/Vertex path."""
    global _last_gemini_request_at
    elapsed = time.monotonic() - _last_gemini_request_at
    remaining = GEMINI_REQUEST_INTERVAL_SECONDS - elapsed
    if remaining > 0:
        time.sleep(remaining)
    _last_gemini_request_at = time.monotonic()


@retry(
    retry=retry_if_exception(_is_retryable_api_error),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(6),
)
def _call_llm_openrouter(chunk_text: str) -> str:
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


@retry(
    retry=retry_if_exception(_is_retryable_api_error),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(6),
)
def _call_llm_gemini(chunk_text: str) -> str:
    """Ask Gemini (via a Vertex AI Express-Mode API key) to extract
    entities/relationships from a chunk of text. Same retry policy as the
    OpenRouter path. "Thinking" is explicitly disabled (thinkingBudget=0) -
    this is plain structured extraction, not multi-step reasoning, and
    testing showed thinking tokens alone were ~9x the rest of the token
    cost with no quality gain. Returns the raw response text."""
    api_key = require_gemini_config()

    _throttle_gemini()
    response = requests.post(
        GEMINI_API_URL,
        headers={"x-goog-api-key": api_key},
        json={
            "contents": [
                {"role": "user", "parts": [{"text": f"{EXTRACTION_SYSTEM_PROMPT}\n\nPassage:\n{chunk_text}"}]}
            ],
            "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}},
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def call_llm(chunk_text: str) -> str:
    """Extract entities/relationships from a chunk via whichever backend is
    configured - Gemini if GEMINI_KEY is set, OpenRouter otherwise (see
    module docstring)."""
    if USE_GEMINI:
        return _call_llm_gemini(chunk_text)
    return _call_llm_openrouter(chunk_text)


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
        if isinstance(item, dict)
        and {"from", "relation", "to"} <= item.keys()
        # Not just "the keys exist" - a model can return a key with a null
        # or empty value (seen for real: {"from": null, ...}), and
        # NetworkX's add_edge() raises ValueError on a None node, which
        # would otherwise crash the whole run on one bad chunk.
        and all(isinstance(item[k], str) and item[k].strip() for k in ("from", "relation", "to"))
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


# How often (in chunks processed) to save a checkpoint during a long build.
# Without this, a run that's interrupted after hours of real, paid API
# calls (killed by a session restart, a closed laptop lid, anything) loses
# every edge extracted so far, since save_graph() previously only ran once
# at the very end. This is a plain periodic save, not a different resume
# scheme - see --resume on main() for how a checkpoint gets picked back up.
GRAPH_CHECKPOINT_INTERVAL = int(os.environ.get("GRAPH_CHECKPOINT_INTERVAL", "50"))


def processed_chunk_ids(graph: nx.MultiDiGraph) -> set[str]:
    """Every source_chunk_id already represented by an edge in `graph` -
    used by --resume to avoid re-processing (and re-paying for) chunks a
    prior, interrupted run already handled."""
    return {data["source_chunk_id"] for _, _, data in graph.edges(data=True)}


def _extract_relations_for_chunk(chunk: dict) -> tuple[dict, list[dict] | None, str | None]:
    """Do the I/O-bound work (LLM call + parse) for one chunk.

    Touches no shared state - safe to run in a worker thread. Returns
    (chunk, relations_or_None, error_message_or_None).
    """
    try:
        raw_content = call_llm(chunk["text"])
    except Exception as exc:  # noqa: BLE001 - one bad chunk must not stop the run
        return chunk, None, str(exc)

    relations = parse_relations(raw_content)
    if relations is None:
        return chunk, None, "could not parse a JSON array from the LLM response"
    return chunk, relations, None


def _apply_chunk_result(
    chunk: dict,
    relations: list[dict] | None,
    error: str | None,
    graph: nx.MultiDiGraph,
    stats: GraphBuildStats,
) -> None:
    """Apply one chunk's already-computed extraction result to the graph
    and stats, and checkpoint if due. Only ever called from the main
    thread - graph/stats mutation is not thread-safe, and isn't meant to
    be; concurrency lives entirely in _extract_relations_for_chunk."""
    if error is not None:
        print(f"WARNING: skipping chunk {chunk['chunk_id']}: {error}")
        stats.chunks_skipped += 1
        stats.skipped_chunk_ids.append(chunk["chunk_id"])
        return

    assert relations is not None  # guaranteed by _extract_relations_for_chunk's contract
    for relation in relations:
        # parse_relations() already validates from/relation/to are
        # non-empty strings, but this is a multi-hour job paid for in
        # real money - one more layer of defense so a case that slips
        # past that filter skips just this one edge instead of crashing
        # the entire run (this exact call previously died on add_edge()
        # rejecting a None node from an unvalidated chunk).
        try:
            graph.add_edge(
                relation["from"],
                relation["to"],
                relation=relation["relation"],
                source_chunk_id=chunk["chunk_id"],
                trust_tier=chunk["trust_tier"],
            )
            stats.edges_added += 1
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING: skipping one malformed relation from chunk {chunk['chunk_id']}: {exc}")

    stats.chunks_processed += 1

    if stats.chunks_processed % GRAPH_CHECKPOINT_INTERVAL == 0:
        save_graph(graph)
        print(
            f"  ...checkpoint: {stats.chunks_processed} chunks processed, "
            f"{graph.number_of_edges()} edges so far (saved to {GRAPH_PATH.name})"
        )


def build_graph(
    chunks: list[dict],
    stats: GraphBuildStats,
    graph: nx.MultiDiGraph | None = None,
    workers: int = 1,
) -> nx.MultiDiGraph:
    """Extract entities/relationships for each chunk and add them as edges.

    `graph` lets a caller resume into an already-partially-built graph
    (see --resume); defaults to a fresh empty one. Checkpoints to
    GRAPH_PATH every GRAPH_CHECKPOINT_INTERVAL chunks so an interruption
    doesn't lose already-paid-for work.

    `workers` > 1 issues LLM calls concurrently via a thread pool - safe
    because each chunk's call is independent and the graph/stats mutation
    that follows is applied back on the main thread, one result at a
    time. Default is 1 (fully sequential, the original behavior) since
    that's the only path that's been run against real free-tier API
    limits; concurrency is only advisable against a backend confirmed not
    to rate-limit at that volume (see GEMINI_KEY / Vertex AI Express Mode
    in the module docstring - confirmed empirically with 10 back-to-back
    calls, zero 429s).
    """
    if graph is None:
        graph = nx.MultiDiGraph()

    if workers <= 1:
        for chunk in chunks:
            c, relations, error = _extract_relations_for_chunk(chunk)
            _apply_chunk_result(c, relations, error, graph, stats)
        return graph

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for c, relations, error in executor.map(_extract_relations_for_chunk, chunks):
            _apply_chunk_result(c, relations, error, graph, stats)

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
        "chunk - fine with GEMINI_KEY set (Vertex AI Express Mode, "
        "no published rate limit hit in testing); only advisable on "
        "OpenRouter with a paid balance, since its free tier is "
        "50 requests/day.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue from data/graph.gpickle instead of starting fresh, "
        "skipping chunks whose source_chunk_id is already in it. For "
        "picking a long build back up after an interruption - normal "
        "reruns should NOT use this (they intentionally rebuild fresh, "
        "see the module docstring).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of chunks to process concurrently via a thread pool. "
        "Default 1 (sequential - the only mode run against a real "
        "free-tier API limit so far). Only raise this against a backend "
        "confirmed not to rate-limit at that concurrency - e.g. Gemini "
        "via GEMINI_KEY, which handled 10 back-to-back calls with zero "
        "429s in testing.",
    )
    args = parser.parse_args()

    try:
        require_gemini_config() if USE_GEMINI else require_openrouter_config()
        chunks = fetch_all_chunks(max_chunks=args.max_chunks)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None

    if not chunks:
        raise SystemExit(
            "No chunks found in the archive_chunks collection - run ingest.py first"
        )

    graph = None
    if args.resume:
        if not GRAPH_PATH.exists():
            raise SystemExit(f"--resume given but {GRAPH_PATH} does not exist")
        with open(GRAPH_PATH, "rb") as f:
            graph = pickle.load(f)
        already_done = processed_chunk_ids(graph)
        before = len(chunks)
        chunks = [c for c in chunks if c["chunk_id"] not in already_done]
        print(
            f"Resuming from {GRAPH_PATH.name}: {graph.number_of_edges()} edges "
            f"already present, skipping {before - len(chunks)} already-processed "
            f"chunks ({len(chunks)} remaining)"
        )

    print(f"LLM backend: {'Gemini (' + GEMINI_MODEL + ', Vertex AI Express Mode)' if USE_GEMINI else 'OpenRouter'}")
    print(f"Chunks to process: {len(chunks)}")

    stats = GraphBuildStats()
    graph = build_graph(chunks, stats, graph=graph, workers=args.workers)
    save_graph(graph)
    print_summary(graph, stats)


if __name__ == "__main__":
    main()
