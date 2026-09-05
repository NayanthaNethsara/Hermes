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
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

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


def _is_retryable_api_error(exc: BaseException) -> bool:
    """True for transient errors worth retrying (network hiccup, timeout,
    429 rate-limit, 5xx, or a 404 from OpenRouter) - False for other 4xx
    client errors (malformed request, bad auth), which are deterministic
    and will fail identically on every retry.

    404 is retried here because OpenRouter's free-tier models return it
    for "this model is temporarily unavailable for free" - a transient
    provider-capacity issue, not a permanent one. A genuinely bad/unknown
    model ID gets a 400 from OpenRouter instead (confirmed empirically),
    so this doesn't mask real config typos."""
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return exc.response.status_code in (404, 429) or exc.response.status_code >= 500
    return isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))


@retry(
    retry=retry_if_exception(_is_retryable_api_error),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(6),
)
def _call_llm(question: str, chunks_so_far: list[dict]) -> str:
    """Ask the configured OpenRouter model for the next search query (or
    DONE). Retries with exponential backoff (2s, 4s, 8s, 16s, 30s - ~60s total) on transient
    errors since the free tier rate-limits - not on a 4xx client error,
    which would never succeed no matter how many retries. Returns the raw
    response content."""
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

    raw = _call_llm(question, chunks_so_far)
    return _clean_query(raw)


def _clean_query(raw: str) -> str:
    """Reduce a model reply to a usable search query, or DONE.

    Small models don't always honour "respond with ONLY the query" - they
    add a preamble line, wrap it in quotes, or write "DONE." with a full
    stop. Take the last non-empty line (the query usually comes after any
    preamble) and strip the decoration.
    """
    lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
    if not lines:
        return DONE

    candidate = lines[-1].strip().strip('"').strip("'").strip()

    # "DONE", "DONE.", "done!" etc. all mean stop searching.
    if candidate.rstrip(".!").strip().upper() == DONE:
        return DONE
    # Also catch a preamble like: I think we have enough. DONE
    if any(line.rstrip(".!").strip().upper() == DONE for line in lines):
        return DONE

    return candidate


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "test question"
    print(plan_next_search(q, []))
