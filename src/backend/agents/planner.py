"""Planner agent: decides what to search next, or whether to stop.

Exports plan_next_search(question, chunks_so_far), which asks an LLM
(via OpenRouter) to either propose the next, more specific search query
to run, or return the literal string "DONE" once it believes enough has
been gathered to answer the question.

This file does one job only - no retrieval, no critic/synthesizer logic.
"""

from __future__ import annotations

import os

import requests
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

DONE = "DONE"

PLANNER_SYSTEM_PROMPT = (
    "You are a research planner searching an archive to answer a "
    "question. Given the question and what has been retrieved so far, "
    "respond with ONLY one of two things:\n"
    "1. A new, more specific search query (plain text, no quotes, no "
    'explanation) that would help find more relevant evidence, or\n'
    f'2. The single word "{DONE}" if the evidence gathered so far is '
    "already enough to fully answer the question.\n"
    "Do not add any other text to your response."
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
    if not chunks_so_far:
        return "(nothing retrieved yet)"
    lines = [f"- [{c['source_doc']}] {c['text'][:200]}" for c in chunks_so_far]
    return "\n".join(lines)


@retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(5))
def _call_llm(question: str, chunks_so_far: list[dict]) -> str:
    """Ask the configured OpenRouter model for the next search query (or
    DONE). Retries with exponential backoff (1s, 2s, 4s, 8s) since the
    free tier rate-limits. Returns the raw response content."""
    api_key, base_url, model = require_openrouter_config()

    user_prompt = (
        f"Question: {question}\n\n"
        f"Retrieved so far:\n{_format_chunks_so_far(chunks_so_far)}\n\n"
        "What should be searched next, or is this enough?"
    )

    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def plan_next_search(question: str, chunks_so_far: list[dict]) -> str:
    """Return the next search query to run, or "DONE" if enough evidence
    has already been gathered to answer `question`.

    `chunks_so_far` uses the same shape returned by
    src.backend.retrieval.vector_search.search_chunks.
    """
    require_openrouter_config()

    raw = _call_llm(question, chunks_so_far).strip().strip('"').strip("'")
    if raw.strip().upper() == DONE:
        return DONE
    return raw


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "test question"
    print(plan_next_search(q, []))
