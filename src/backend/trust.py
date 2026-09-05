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
from itertools import combinations
from pathlib import Path

import requests
from dotenv import load_dotenv
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

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


def require_openrouter_config() -> tuple[str, str, str]:
    """Fetch OpenRouter config or fail fast with a clear message.

    Checked up front (not inside the retried call_llm) so a missing key
    fails immediately instead of being retried five times by tenacity and
    surfacing as an opaque RetryError.
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
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(5),
)
def _call_llm(chunk_a: dict, chunk_b: dict) -> str:
    """Ask the configured OpenRouter model whether two passages conflict.
    Retries with exponential backoff (1s, 2s, 4s, 8s) on transient errors
    since the free tier rate-limits - not on a 4xx client error, which
    would never succeed no matter how many retries. Returns the raw
    response content."""
    api_key, base_url, model = require_openrouter_config()

    user_prompt = (
        f"Passage A (source: {chunk_a['source_doc']}):\n{chunk_a['text']}\n\n"
        f"Passage B (source: {chunk_b['source_doc']}):\n{chunk_b['text']}\n\n"
        "Do these two passages agree, or do they conflict on a specific fact? "
        'Answer in JSON: {"conflict": true/false, "topic": "..."}'
    )

    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": CONTRADICTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


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

    contradictions = []
    new_calls_made = 0

    for chunk_a, chunk_b in _rank_candidate_pairs(chunks):
        key = _pair_key(chunk_a, chunk_b)

        if key in _verdict_cache:
            result = _verdict_cache[key]
        else:
            if new_calls_made >= MAX_PAIRS_CHECKED:
                # Budget for this call spent; remaining pairs stay
                # uncompared for now (a later hop can pick them up).
                break
            try:
                raw_content = _call_llm(chunk_a, chunk_b)
                result = _parse_conflict_response(raw_content)
            except Exception as exc:  # noqa: BLE001 - one bad pair must not stop the check
                print(
                    f"WARNING: skipping contradiction check for "
                    f"{chunk_a['chunk_id']} / {chunk_b['chunk_id']}: {exc}"
                )
                continue
            new_calls_made += 1

            if result is None:
                print(
                    f"WARNING: could not parse contradiction-check response for "
                    f"{chunk_a['chunk_id']} / {chunk_b['chunk_id']}"
                )
            _verdict_cache[key] = result

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
