"""Planner agent: decides what to search next, or whether to stop.

Exports plan_next_search(question, chunks_so_far), which asks an LLM
(via OpenRouter) to either propose the next, more specific search query
to run, or return the literal string "DONE" once it believes enough has
been gathered to answer the question.

This file does one job only - no retrieval, no critic/synthesizer logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from dotenv import load_dotenv  # noqa: E402

from src.backend import llm  # noqa: E402
from src.backend.llm import require_openrouter_config  # noqa: E402,F401

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


def _format_chunks_so_far(chunks_so_far: list[dict]) -> str:
    if not chunks_so_far:
        return "(nothing retrieved yet)"
    lines = [f"- [{c['source_doc']}] {c['text'][:200]}" for c in chunks_so_far]
    return "\n".join(lines)


def _call_llm(question: str, chunks_so_far: list[dict]) -> str:
    """Ask the LLM for the next search query (or DONE).

    Retries and model failover are handled by src.backend.llm.chat.
    Returns the raw response content.
    """
    user_prompt = (
        f"Question: {question}\n\n"
        f"Retrieved so far:\n{_format_chunks_so_far(chunks_so_far)}\n\n"
        "What should be searched next, or is this enough?"
    )
    return llm.chat(PLANNER_SYSTEM_PROMPT, user_prompt)


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
