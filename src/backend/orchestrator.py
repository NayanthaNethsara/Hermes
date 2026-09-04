"""The agent loop: Planner -> Retriever -> Critic -> repeat, then Synthesizer.

Exports run_archivist(question), which ties together the planner, critic,
synthesizer, and retrieval (vector + graph search) into the search loop
described in docs/architecture.md section 3.

This reads as a simple loop, not a framework - no external agent library,
just the functions built in the previous prompts.

How to run it:
    From the repo root, with a real corpus already ingested
    (src/ingestion/ingest.py and build_graph.py) and OPENROUTER_API_KEY /
    VOYAGE_API_KEY set in .env:
        python -m src.backend.orchestrator "your question here"
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.backend.agents import critic, planner, synthesizer  # noqa: E402
from src.backend.retrieval import graph_search, vector_search  # noqa: E402

# Hard cap on search hops - protects API budget and demo reliability
# (CLAUDE.md rule 6). Enforced with a plain loop counter, never unbounded.
MAX_HOPS = 5

UNCERTAINTY_NOTE = (
    "\n\n(Note: the search was stopped after the maximum number of hops "
    "without the evidence being confirmed as fully sufficient. Be honest "
    "in your answer about this uncertainty, rather than presenting the "
    "evidence gathered so far as a complete picture.)"
)


def _extract_entity_candidates(text: str) -> list[str]:
    """Naive proper-noun heuristic: capitalized word sequences.

    Used to decide whether a search query "involves connected entities"
    (architecture.md 4.3) worth walking the knowledge graph for, without
    needing a full NER model.
    """
    seen: set[str] = set()
    entities: list[str] = []
    for match in re.findall(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b", text):
        if match not in seen:
            seen.add(match)
            entities.append(match)
    return entities


def _gather_chunks(query: str, seen_chunk_ids: set[str]) -> list[dict]:
    """Run vector search, plus graph search when the query names specific
    entities, and return only the chunks not already in seen_chunk_ids
    (deduplicated against each other too)."""
    candidates = list(vector_search.search_chunks(query))

    entities = _extract_entity_candidates(query)
    if entities:
        try:
            edges = graph_search.search_graph(entities)
        except RuntimeError as exc:
            # The knowledge graph is an optional enhancement over vector
            # search, not a hard requirement - if build_graph.py hasn't
            # been run yet, keep going with vector-only results.
            print(f"WARNING: graph search skipped: {exc}")
            edges = []

        known_ids = {c["chunk_id"] for c in candidates} | seen_chunk_ids
        edge_chunk_ids = {
            edge["source_chunk_id"] for edge in edges if edge.get("source_chunk_id")
        }
        new_ids = edge_chunk_ids - known_ids
        if new_ids:
            candidates.extend(vector_search.get_chunks_by_ids(list(new_ids)))

    new_chunks = []
    local_seen: set[str] = set()
    for chunk in candidates:
        chunk_id = chunk["chunk_id"]
        if chunk_id in seen_chunk_ids or chunk_id in local_seen:
            continue
        local_seen.add(chunk_id)
        new_chunks.append(chunk)

    return new_chunks


def run_archivist(question: str) -> dict:
    """Answer `question` by running the Planner/Retriever/Critic loop
    (up to MAX_HOPS times) and then handing everything gathered to the
    Synthesizer.

    Returns exactly: {"answer", "reasoning_steps", "sources",
    "contradictions"} - the API contract in docs/architecture.md
    section 6.
    """
    chunks_so_far: list[dict] = []
    seen_chunk_ids: set[str] = set()
    reasoning_steps: list[dict] = []
    contradictions: list[dict] = []
    hit_hop_cap = True

    for hop in range(1, MAX_HOPS + 1):
        query = planner.plan_next_search(question, chunks_so_far)
        if query == planner.DONE:
            hit_hop_cap = False
            break

        new_chunks = _gather_chunks(query, seen_chunk_ids)
        seen_chunk_ids.update(c["chunk_id"] for c in new_chunks)
        chunks_so_far.extend(new_chunks)

        critic_result = critic.evaluate_evidence(question, chunks_so_far)
        contradictions = critic_result["contradictions"]

        reasoning_steps.append(
            {
                "step": hop,
                "action": f"Searched: '{query}'",
                "found": f"{len(new_chunks)} relevant chunks",
            }
        )

        if critic_result["enough"]:
            hit_hop_cap = False
            break
    else:
        # The for loop ran all MAX_HOPS iterations without break-ing out
        # via DONE or critic satisfaction - the hop cap was hit.
        hit_hop_cap = True

    synthesis_question = question + UNCERTAINTY_NOTE if hit_hop_cap else question
    result = synthesizer.write_answer(synthesis_question, chunks_so_far, contradictions)

    return {
        "answer": result["answer"],
        "reasoning_steps": reasoning_steps,
        "sources": result["sources"],
        "contradictions": contradictions,
    }


if __name__ == "__main__":
    import json

    q = sys.argv[1] if len(sys.argv) > 1 else "test question"
    print(json.dumps(run_archivist(q), indent=2))
