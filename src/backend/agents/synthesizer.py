"""Synthesizer agent: writes the final answer from gathered evidence.

Exports write_answer(question, chunks, contradictions), which asks an LLM
to write the answer text using only the given chunks - never outside
knowledge, since this is a fictional corpus - and assembles the sources
list deterministically from those same chunks (not from the LLM, which
keeps citations accurate).

This file does one job only - no retrieval, no planner/critic logic.
"""

from __future__ import annotations

import os

import requests
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

SNIPPET_LENGTH = 160

BASE_SYSTEM_PROMPT = (
    "You are an archivist answering questions using only the evidence "
    "passages you are given below. Do not use any outside or general "
    "knowledge - this is a fictional archive, and every claim in your "
    "answer must be traceable to one of the given passages. If the "
    "passages don't fully answer the question, say so honestly rather "
    "than guessing. Write the answer as plain prose, no JSON, no markdown."
)

CONTRADICTION_INSTRUCTION = (
    " Some of the evidence passages conflict with each other on a "
    "specific fact (see the noted contradictions below). Your answer "
    "must explicitly mention that the sources disagree, rather than "
    "silently picking one side and presenting it as settled fact."
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


def _format_chunks(chunks: list[dict]) -> str:
    if not chunks:
        return "(no evidence was found)"
    lines = [f"- [{c['source_doc']}] {c['text']}" for c in chunks]
    return "\n".join(lines)


def _format_contradictions(contradictions: list[dict]) -> str:
    if not contradictions:
        return ""
    lines = [
        f"- {c['topic']}: {' vs. '.join(c['sources_disagree'])}"
        for c in contradictions
    ]
    return "\n\nNoted contradictions:\n" + "\n".join(lines)


@retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(5))
def _call_llm(question: str, chunks: list[dict], contradictions: list[dict]) -> str:
    """Ask the configured OpenRouter model to write the final answer.
    Retries with exponential backoff (1s, 2s, 4s, 8s) since the free tier
    rate-limits. Returns the raw response content (plain-text answer)."""
    api_key, base_url, model = require_openrouter_config()

    system_prompt = BASE_SYSTEM_PROMPT
    if contradictions:
        system_prompt += CONTRADICTION_INSTRUCTION

    user_prompt = (
        f"Question: {question}\n\n"
        f"Evidence passages:\n{_format_chunks(chunks)}"
        f"{_format_contradictions(contradictions)}\n\n"
        "Write the final answer."
    )

    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _source_entry(chunk: dict) -> dict:
    title = chunk["source_doc"]
    if chunk.get("page") is not None:
        title = f"{title}, p.{chunk['page']}"

    text = chunk["text"]
    snippet = text[:SNIPPET_LENGTH].strip()
    if len(text) > SNIPPET_LENGTH:
        snippet += "..."

    return {"title": title, "trust": chunk["trust_tier"], "snippet": snippet}


def write_answer(question: str, chunks: list[dict], contradictions: list[dict]) -> dict:
    """Write the final answer to `question` using only `chunks` as evidence.

    `chunks` uses the same shape returned by
    src.backend.retrieval.vector_search.search_chunks. `contradictions`
    uses the shape returned by src.backend.trust.detect_contradictions.

    Returns exactly: {"answer": str, "sources": [...]}, matching the
    final API response shape in docs/architecture.md section 6. The
    sources list is built directly from `chunks` (not from the LLM), so
    citations always match the evidence that was actually used.
    """
    require_openrouter_config()

    answer = _call_llm(question, chunks, contradictions).strip()
    sources = [_source_entry(chunk) for chunk in chunks]

    return {"answer": answer, "sources": sources}


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "test question"
    print(write_answer(q, [], []))
