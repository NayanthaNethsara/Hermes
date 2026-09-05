"""Synthesizer agent: writes the final answer from gathered evidence.

Exports write_answer(question, chunks, contradictions), which asks an LLM
to write the answer text using only the given chunks - never outside
knowledge, since this is a fictional corpus - and assembles the sources
list deterministically from those same chunks (not from the LLM, which
keeps citations accurate).

This file does one job only - no retrieval, no planner/critic logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from dotenv import load_dotenv  # noqa: E402

from src.backend import llm  # noqa: E402
from src.backend.llm import require_openrouter_config  # noqa: E402,F401

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


def _call_llm(question: str, chunks: list[dict], contradictions: list[dict]) -> str:
    """Ask the LLM to write the final answer.

    Retries and model failover are handled by src.backend.llm.chat.
    Returns the raw response content (plain-text answer).
    """
    system_prompt = BASE_SYSTEM_PROMPT
    if contradictions:
        system_prompt += CONTRADICTION_INSTRUCTION

    user_prompt = (
        f"Question: {question}\n\n"
        f"Evidence passages:\n{_format_chunks(chunks)}"
        f"{_format_contradictions(contradictions)}\n\n"
        "Write the final answer."
    )
    return llm.chat(system_prompt, user_prompt)


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
