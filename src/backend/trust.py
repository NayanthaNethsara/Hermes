"""Trust tier data and cross-chunk contradiction detection.

No FastAPI or agent logic here - just:
- TRUST_TIERS: the source_type -> trust_tier lookup, for reference
  anywhere else in the codebase that needs it.
- detect_contradictions(chunks): checks a small, cheap-to-compute set of
  chunk pairs for factual conflicts via an LLM call, and returns them in
  the exact shape the "contradictions" field of the API contract expects
  (docs/architecture.md section 6).
"""

from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv  # noqa: E402

from src.backend import llm  # noqa: E402
from src.backend.llm import require_openrouter_config  # noqa: E402,F401

load_dotenv()

# source_type -> trust_tier, per docs/architecture.md section 5.
TRUST_TIERS = {
    "codex": "high",
    "wiki": "medium",
    "novel": "medium-low",
    "ephemera": "low",
}

# Max *new* LLM comparisons per detect_contradictions() call. Already-compared
# pairs come from the cache below and don't count against this budget.
# Tunable via .env because this is the single biggest consumer of the
# OpenRouter free-tier request budget (see SETUP.md "API budget").
MAX_PAIRS_CHECKED = int(os.environ.get("CONTRADICTION_MAX_PAIRS", "5"))

# How many contradiction checks to run at once. These are independent,
# network-bound calls, so running them concurrently cuts the slowest part
# of a hop from (pairs x per-call latency) down to roughly one call.
# Kept modest to stay well inside OpenRouter's ~20 requests/minute free
# tier - raising it risks trading latency for 429s.
CONTRADICTION_WORKERS = int(os.environ.get("CONTRADICTION_WORKERS", "5"))

# Verdicts already obtained from the LLM, keyed by the pair of chunk_ids.
# The orchestrator calls the critic once per search hop on a growing
# chunk list, so without this the same pairs get re-sent to the LLM every
# hop - which burns the free-tier request budget fast (architecture.md
# section 9: ~50 requests/day). Process-lifetime only; the corpus is
# fixed, so a verdict for a given pair never changes.
_verdict_cache: dict[frozenset, dict | None] = {}

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "is",
    "was", "were", "it", "that", "this", "with", "for", "as", "by", "be",
    "been", "has", "have", "had", "its", "their", "his", "her", "who",
    "which", "from", "but", "not", "no", "so", "than", "then", "when",
    "where", "after", "before", "during", "into", "onto", "upon", "over",
    "under", "there", "these", "those", "such", "also",
}

CONTRADICTION_SYSTEM_PROMPT = (
    "You compare two passages and decide whether they conflict on a "
    "specific fact, or agree. Respond with ONLY a JSON object (no prose, "
    'no markdown fences), shaped like: {"conflict": true, "topic": '
    '"short description of the disputed fact"} or {"conflict": false, '
    '"topic": ""}.'
)



def _keywords(text: str) -> set[str]:
    """Lowercase, stopword-free keyword set used for a cheap overlap score."""
    words = re.findall(r"[a-zA-Z']+", text.lower())
    return {w for w in words if len(w) > 3 and w not in _STOPWORDS}


def _rank_candidate_pairs(chunks: list[dict]) -> list[tuple[dict, dict]]:
    """Rank the pairs most likely to be about the same topic or fact.

    Scores every pair by simple keyword overlap (cheap, no API calls),
    drops pairs from the same source_doc (a "contradiction" needs two
    different sources) and pairs with zero overlap (clearly unrelated).
    Returns them best-first; the caller decides how many to actually
    spend an LLM call on.
    """
    scored = []
    for chunk_a, chunk_b in combinations(chunks, 2):
        if chunk_a["source_doc"] == chunk_b["source_doc"]:
            continue
        overlap = len(_keywords(chunk_a["text"]) & _keywords(chunk_b["text"]))
        if overlap > 0:
            scored.append((overlap, chunk_a, chunk_b))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [(a, b) for _, a, b in scored]


def _pair_key(chunk_a: dict, chunk_b: dict) -> frozenset:
    return frozenset((chunk_a["chunk_id"], chunk_b["chunk_id"]))


def _check_pair(chunk_a: dict, chunk_b: dict) -> dict | None:
    """Ask the LLM whether one pair conflicts, returning the parsed verdict.

    Safe to run in a worker thread: it touches no shared state and never
    raises, so one bad pair can't take down the whole check.
    """
    try:
        return _parse_conflict_response(_call_llm(chunk_a, chunk_b))
    except Exception as exc:  # noqa: BLE001 - one bad pair must not stop the check
        print(
            f"WARNING: skipping contradiction check for "
            f"{chunk_a['chunk_id']} / {chunk_b['chunk_id']}: {exc}"
        )
        return None


def _call_llm(chunk_a: dict, chunk_b: dict) -> str:
    """Ask the LLM whether two passages conflict on a specific fact.

    Retries and model failover are handled by src.backend.llm.chat.
    Returns the raw response content.
    """
    user_prompt = (
        f"Passage A (source: {chunk_a['source_doc']}):\n{chunk_a['text']}\n\n"
        f"Passage B (source: {chunk_b['source_doc']}):\n{chunk_b['text']}\n\n"
        "Do these two passages agree, or do they conflict on a specific fact? "
        'Answer in JSON: {"conflict": true/false, "topic": "..."}'
    )
    return llm.chat(CONTRADICTION_SYSTEM_PROMPT, user_prompt)


def _parse_conflict_response(raw_content: str) -> dict | None:
    """Parse the LLM's {"conflict": ..., "topic": ...} response.

    Returns None (rather than raising) if the response isn't valid JSON,
    so the caller can skip the pair and keep going instead of crashing
    the whole check over one bad response.
    """
    candidate = raw_content.strip()

    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1).strip()

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        brace_match = re.search(r"\{.*\}", candidate, re.DOTALL)
        if not brace_match:
            return None
        try:
            parsed = json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(parsed, dict) or "conflict" not in parsed:
        return None
    return parsed


def detect_contradictions(chunks: list[dict]) -> list[dict]:
    """Check a bounded set of chunk pairs for factual conflicts.

    `chunks` uses the same shape returned by
    src.backend.retrieval.vector_search.search_chunks (keys: chunk_id,
    text, source_doc, page, source_type, trust_tier).

    Rather than comparing every pair (expensive as chunk count grows),
    this ranks pairs by simple keyword overlap and spends at most
    MAX_PAIRS_CHECKED *new* LLM calls per invocation. Pairs already
    compared earlier in this process are served from _verdict_cache, so
    they still surface here without costing another request.

    Returns a list shaped like:
        [{"topic": "...", "sources_disagree": ["source_doc_1", "source_doc_2"]}]
    matching the "contradictions" field in the API contract
    (docs/architecture.md section 6).
    """
    if len(chunks) < 2:
        return []

    # Fail fast on a missing/incomplete OpenRouter config, rather than
    # letting it surface as a per-pair RetryError from inside _call_llm
    # (which is retried and would otherwise burn through 5 backoff
    # attempts before the caller ever finds out why).
    require_openrouter_config()

    ranked_pairs = list(_rank_candidate_pairs(chunks))

    # Work out which pairs actually need an LLM call before making any, so
    # they can be run together instead of one after another.
    pending: list[tuple[dict, dict]] = []
    for chunk_a, chunk_b in ranked_pairs:
        if _pair_key(chunk_a, chunk_b) in _verdict_cache:
            continue
        if len(pending) >= MAX_PAIRS_CHECKED:
            break
        pending.append((chunk_a, chunk_b))

    if pending:
        # Each check is an independent ~4s wait on the network, so running
        # them concurrently turns the slowest part of a hop from
        # (pairs x 4s) into roughly 4s. Verdicts are collected here and
        # written to the shared cache on this thread afterwards, so no
        # worker mutates state the others can see.
        workers = min(len(pending), CONTRADICTION_WORKERS)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            verdicts = list(pool.map(lambda pair: _check_pair(*pair), pending))

        for (chunk_a, chunk_b), result in zip(pending, verdicts):
            if result is None:
                print(
                    f"WARNING: no usable contradiction verdict for "
                    f"{chunk_a['chunk_id']} / {chunk_b['chunk_id']}"
                )
            _verdict_cache[_pair_key(chunk_a, chunk_b)] = result

    # Assemble in ranked order so output stays deterministic regardless of
    # the order the concurrent checks happened to finish in.
    contradictions = []
    for chunk_a, chunk_b in ranked_pairs:
        result = _verdict_cache.get(_pair_key(chunk_a, chunk_b))
        if result and result.get("conflict"):
            contradictions.append(
                {
                    "topic": result.get("topic") or "unspecified",
                    "sources_disagree": [chunk_a["source_doc"], chunk_b["source_doc"]],
                }
            )

    return contradictions


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.backend.retrieval.vector_search import search_chunks

    query = sys.argv[1] if len(sys.argv) > 1 else "test query"
    found_chunks = search_chunks(query, top_k=5)
    print(detect_contradictions(found_chunks))
