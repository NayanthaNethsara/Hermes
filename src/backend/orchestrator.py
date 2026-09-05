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

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

load_dotenv()

from src.backend.agents import critic, planner, synthesizer  # noqa: E402
from src.backend.retrieval import graph_search, vector_search  # noqa: E402

# Hard cap on search hops - protects API budget and demo reliability
# (CLAUDE.md rule 6). Enforced with a plain loop counter, never unbounded.
# Lowerable via .env to save free-tier requests, but never raisable above
# 5: the rule is a hard ceiling, so the env value is clamped, not trusted.
HARD_MAX_HOPS = 5
MAX_HOPS = min(int(os.environ.get("MAX_SEARCH_HOPS", HARD_MAX_HOPS)), HARD_MAX_HOPS)

UNCERTAINTY_NOTE = (
    "\n\n(Note: the search was stopped after the maximum number of hops "
    "without the evidence being confirmed as fully sufficient. Be honest "
    "in your answer about this uncertainty, rather than presenting the "
    "evidence gathered so far as a complete picture.)"
)


# Capitalized words that start a sentence/question but aren't entities.
# Without this filter, "Who repaired the Ember Clock" yields "Who", and
# graph_search's case-insensitive substring match would happily match it
# against unrelated nodes like "Whorl Keeper".
_NON_ENTITY_WORDS = {
    "who", "what", "when", "where", "why", "how", "which", "whose", "whom",
    "did", "does", "do", "is", "are", "was", "were", "the", "a", "an",
    "list", "find", "search", "tell", "explain", "describe", "give",
    # Sentence-openers that get capitalized and were previously treated as
    # entities. "In" was the worst offender: capitalized at the start of a
    # real question, it substring-matched every node containing "in"
    # (Cinder, Ring, Iron...) and pulled 88% of the corpus into one prompt.
    "in", "on", "at", "of", "to", "for", "by", "with", "from", "as", "into",
    "state", "trace", "name", "according", "summarise", "summarize",
    "there", "any", "some", "this", "that", "these", "those", "it",
}

# Ignore capitalized fragments shorter than this - they're stray words, not
# names, and short strings match far too many graph nodes to be useful.
_MIN_ENTITY_LENGTH = 3

# Upper bound on how many chunks a single hop may pull in via the knowledge
# graph. Graph walks fan out fast, and every chunk retrieved here is fed to
# the Critic and Synthesizer on every subsequent hop - so an uncapped walk
# both destroys answer quality (the real signal is buried) and burns tokens.
MAX_GRAPH_CHUNKS_PER_HOP = 15

# Upper bound on the evidence passed to the Synthesizer in its single
# final call. See _chunks_for_synthesis for why this matters.
MAX_SYNTHESIS_CHUNKS = int(os.environ.get("MAX_SYNTHESIS_CHUNKS", "25"))


def _extract_entity_candidates(text: str) -> list[str]:
    """Naive proper-noun heuristic: capitalized word sequences.

    Used to decide whether a search query "involves connected entities"
    (architecture.md 4.3) worth walking the knowledge graph for, without
    needing a full NER model.
    """
    seen: set[str] = set()
    entities: list[str] = []
    for match in re.findall(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b", text):
        if match.lower() in _NON_ENTITY_WORDS:
            continue
        # Strip a leading question word from a longer phrase, e.g.
        # "Which Ember Wardens" -> "Ember Wardens".
        words = match.split()
        while words and words[0].lower() in _NON_ENTITY_WORDS:
            words = words[1:]
        cleaned = " ".join(words)
        if len(cleaned) < _MIN_ENTITY_LENGTH:
            continue
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            entities.append(cleaned)
    return entities


_GRAPH_TRUST_PRIORITY = {"high": 0, "medium": 1, "medium-low": 2, "low": 3}


def _rank_graph_chunk_ids(edges: list[dict], known_ids: set[str]) -> list[str]:
    """Pick the best MAX_GRAPH_CHUNKS_PER_HOP chunk ids out of `edges`.

    A chunk referenced by many edges is densely connected to the entities
    in the query, so it's ranked above one mentioned in passing; ties break
    towards the more trustworthy source. Chunks already retrieved
    (`known_ids`) are excluded.
    """
    edge_count: dict[str, int] = {}
    best_trust: dict[str, int] = {}

    for edge in edges:
        chunk_id = edge.get("source_chunk_id")
        if not chunk_id or chunk_id in known_ids:
            continue
        edge_count[chunk_id] = edge_count.get(chunk_id, 0) + 1
        trust = _GRAPH_TRUST_PRIORITY.get(edge.get("trust_tier"), len(_GRAPH_TRUST_PRIORITY))
        if trust < best_trust.get(chunk_id, len(_GRAPH_TRUST_PRIORITY)):
            best_trust[chunk_id] = trust

    ranked = sorted(
        edge_count,
        key=lambda cid: (-edge_count[cid], best_trust[cid], cid),
    )
    return ranked[:MAX_GRAPH_CHUNKS_PER_HOP]


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
        new_ids = _rank_graph_chunk_ids(edges, known_ids)
        if new_ids:
            candidates.extend(vector_search.get_chunks_by_ids(new_ids))

    new_chunks = []
    local_seen: set[str] = set()
    for chunk in candidates:
        chunk_id = chunk["chunk_id"]
        if chunk_id in seen_chunk_ids or chunk_id in local_seen:
            continue
        local_seen.add(chunk_id)
        new_chunks.append(chunk)

    return new_chunks


def _normalize_query(query: str) -> str:
    """Reduce a search query to a form that ignores cosmetic rewording.

    The Planner tends to circle the same search in different words when
    the Critic won't accept the evidence - one real question produced
    "wars won by The Silent Choir", "Which war did The Silent Choir win",
    and "The Silent Choir won which war" across three hops, all
    retrieving the same chunks. Comparing raw strings misses that, so
    queries are compared as a sorted bag of significant words with common
    plurals folded together.
    """
    words = re.findall(r"[a-z]+", query.lower())
    significant = sorted(
        {word.rstrip("s") for word in words if word not in _NON_ENTITY_WORDS}
    )
    # A query made entirely of stopwords/digits normalizes to nothing, and
    # every such query would then look identical to every other. Fall back
    # to the raw text so only genuinely repeated searches are treated as
    # repeats.
    return " ".join(significant) or query.strip().lower()


def _chunks_for_synthesis(chunks_so_far: list[dict]) -> list[dict]:
    """Trim the evidence handed to the Synthesizer to the best chunks.

    `chunks_so_far` accumulates across hops - measured at 80 chunks and
    ~152,000 characters (roughly 38k tokens) by hop 5 on a real question.
    Sending all of that in one prompt is slow, expensive, and past the
    point where a small free-tier model uses it well, since material in
    the middle of a very long prompt tends to be ignored.

    Chunks are kept in retrieval order (earlier hops answered the original
    question more directly) but higher-trust sources are preferred when
    trimming, so the citation list can't end up dominated by the
    least-reliable material.
    """
    if len(chunks_so_far) <= MAX_SYNTHESIS_CHUNKS:
        return chunks_so_far

    ordered = sorted(
        enumerate(chunks_so_far),
        key=lambda pair: (
            _GRAPH_TRUST_PRIORITY.get(pair[1].get("trust_tier"), len(_GRAPH_TRUST_PRIORITY)),
            pair[0],
        ),
    )
    kept = sorted(ordered[:MAX_SYNTHESIS_CHUNKS], key=lambda pair: pair[0])
    return [chunk for _, chunk in kept]


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
    seen_queries: set[str] = set()
    reasoning_steps: list[dict] = []
    contradictions: list[dict] = []
    seen_contradictions: set[tuple] = set()
    hit_hop_cap = True

    for hop in range(1, MAX_HOPS + 1):
        query = planner.plan_next_search(question, chunks_so_far)
        if query == planner.DONE:
            hit_hop_cap = False
            break

        # The Planner re-proposing a search it has already run means it has
        # stopped making progress - usually because the Critic keeps saying
        # "not enough" for evidence that is actually as good as it will get.
        # Continuing just re-retrieves the same chunks and re-runs the
        # contradiction checks: measured at ~15 wasted API calls and ~40
        # wasted seconds on one real question. Stop and answer with what's
        # been gathered instead.
        normalized = _normalize_query(query)
        if normalized in seen_queries:
            print(f"WARNING: planner repeated the search {query!r} - stopping early")
            break
        seen_queries.add(normalized)

        new_chunks = _gather_chunks(query, seen_chunk_ids)
        seen_chunk_ids.update(c["chunk_id"] for c in new_chunks)
        chunks_so_far.extend(new_chunks)

        critic_result = critic.evaluate_evidence(question, chunks_so_far)

        # Accumulate rather than overwrite: a contradiction surfaced on an
        # earlier hop must not disappear just because a later hop's critic
        # sampled a different set of pairs (CLAUDE.md rule 5 - never
        # silently resolve a contradiction).
        for contradiction in critic_result["contradictions"]:
            key = (
                contradiction["topic"],
                tuple(sorted(contradiction["sources_disagree"])),
            )
            if key not in seen_contradictions:
                seen_contradictions.add(key)
                contradictions.append(contradiction)

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
    result = synthesizer.write_answer(
        synthesis_question, _chunks_for_synthesis(chunks_so_far), contradictions
    )

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
