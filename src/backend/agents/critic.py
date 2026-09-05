"""Critic agent: judges whether the gathered evidence is enough, and
surfaces any contradictions between sources.

Exports evaluate_evidence(question, chunks_so_far), which combines
src.backend.trust.detect_contradictions() with an LLM judgment of
sufficiency.

This file does one job only - no retrieval, no planner/synthesizer logic.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# Make sure the repo root is importable so `from src.backend...` resolves
# even when this file is run directly (`python src/backend/agents/critic.py`)
# rather than as a module (`python -m src.backend.agents.critic`).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from src.backend import llm  # noqa: E402
from src.backend.llm import require_openrouter_config  # noqa: E402,F401
from src.backend.trust import detect_contradictions  # noqa: E402

load_dotenv()

CRITIC_SYSTEM_PROMPT = (
    "You judge whether gathered evidence is enough to fully answer a "
    "research question. Respond with ONLY a JSON object (no prose, no "
    'markdown fences), shaped like: {"enough": true} or {"enough": false}.'
)


def _format_chunks_so_far(chunks_so_far: list[dict]) -> str:
    lines = [f"- [{c['source_doc']}] {c['text'][:200]}" for c in chunks_so_far]
    return "\n".join(lines)


def _call_llm(question: str, chunks_so_far: list[dict]) -> str:
    """Ask the LLM whether the evidence gathered so far is enough.

    Retries and model failover are handled by src.backend.llm.chat.
    Returns the raw response content.
    """
    user_prompt = (
        f"Question: {question}\n\n"
        f"Evidence gathered so far:\n{_format_chunks_so_far(chunks_so_far)}\n\n"
        "Is this enough to fully answer the question?"
    )
    return llm.chat(CRITIC_SYSTEM_PROMPT, user_prompt)


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
