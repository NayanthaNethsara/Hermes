"""Critic agent: judges whether the gathered evidence is enough, and
surfaces any contradictions between sources.

Exports evaluate_evidence(question, chunks_so_far), which combines
src.backend.trust.detect_contradictions() with an LLM judgment of
sufficiency.

This file does one job only - no retrieval, no planner/synthesizer logic.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

# Make sure the repo root is importable so `from src.backend...` resolves
# even when this file is run directly (`python src/backend/agents/critic.py`)
# rather than as a module (`python -m src.backend.agents.critic`).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from src.backend.trust import detect_contradictions  # noqa: E402

load_dotenv()

CRITIC_SYSTEM_PROMPT = (
    "You judge whether gathered evidence is enough to fully answer a "
    "research question. Respond with ONLY a JSON object (no prose, no "
    'markdown fences), shaped like: {"enough": true} or {"enough": false}.'
)


def require_openrouter_config() -> tuple[str, str, str]:
    """Fetch OpenRouter config or fail fast with a clear message.

    Checked up front (not inside the retried _call_llm) so a missing key
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


def _format_chunks_so_far(chunks_so_far: list[dict]) -> str:
    lines = [f"- [{c['source_doc']}] {c['text'][:200]}" for c in chunks_so_far]
    return "\n".join(lines)


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
def _call_llm(question: str, chunks_so_far: list[dict]) -> str:
    """Ask the configured OpenRouter model whether the evidence is enough.
    Retries with exponential backoff (1s, 2s, 4s, 8s) on transient errors
    since the free tier rate-limits - not on a 4xx client error, which
    would never succeed no matter how many retries. Returns the raw
    response content."""
    api_key, base_url, model = require_openrouter_config()

    user_prompt = (
        f"Question: {question}\n\n"
        f"Evidence gathered so far:\n{_format_chunks_so_far(chunks_so_far)}\n\n"
        "Is this enough to fully answer the question?"
    )

    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _parse_enough(raw_content: str) -> bool:
    """Parse the LLM's {"enough": ...} response. Defaults to False (keep
    searching) if the response can't be parsed, rather than raising -
    the orchestrator's 5-hop cap is what ultimately bounds the loop."""
    candidate = raw_content.strip()

    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1).strip()

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        brace_match = re.search(r"\{.*\}", candidate, re.DOTALL)
        if not brace_match:
            return False
        try:
            parsed = json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            return False

    if not isinstance(parsed, dict):
        return False
    return bool(parsed.get("enough", False))


def evaluate_evidence(question: str, chunks_so_far: list[dict]) -> dict:
    """Judge whether `chunks_so_far` is enough to fully answer `question`,
    and report any contradictions found among them.

    `chunks_so_far` uses the same shape returned by
    src.backend.retrieval.vector_search.search_chunks.

    Returns exactly: {"enough": bool, "contradictions": [...]}, where
    contradictions is whatever detect_contradictions() returned (may be
    an empty list).
    """
    contradictions = detect_contradictions(chunks_so_far)

    if not chunks_so_far:
        # Nothing retrieved yet - can't possibly be enough, and there is
        # no point spending an API call to ask.
        return {"enough": False, "contradictions": contradictions}

    require_openrouter_config()
    raw = _call_llm(question, chunks_so_far)
    return {"enough": _parse_enough(raw), "contradictions": contradictions}


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "test question"
    print(evaluate_evidence(q, []))
