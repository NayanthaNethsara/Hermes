"""Eval harness: runs a batch of sample questions against the backend and
logs the results for manual review.

Does NOT judge correctness automatically - that needs manual review or a
separate LLM-as-judge step. This script just runs everything against
POST /api/ask and logs it cleanly (question, answer, reasoning step
count, whether a contradiction was flagged, response time) so the team
can review answers by hand.

Run this again after any meaningful backend change (new prompt, model
swap, retrieval tweak, etc.) to track whether things are improving or
regressing over time - that's the whole point of keeping results/
around instead of eyeballing one-off runs.

How to run it:
    1. The FastAPI backend (src/backend/main.py, Prompt 7) must already
       be running locally:
           uvicorn src.backend.main:app --reload
    2. From the repo root:
           python -m src.eval.run_eval --questions-path sample_questions.json

sample_questions.json can be either a JSON array of question strings, or
an array of {"question": "..."} objects.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_PATH = REPO_ROOT / "results" / "eval_log.json"

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
# The agent loop can take a while (up to 5 search hops), so give it room.
REQUEST_TIMEOUT_SECONDS = 90


def load_questions(questions_path: Path) -> list[str]:
    """Load questions from a JSON file: either a list of strings, or a
    list of {"question": "..."} objects."""
    raw = json.loads(questions_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{questions_path} must contain a JSON array")

    questions = []
    for item in raw:
        if isinstance(item, str):
            questions.append(item)
        elif isinstance(item, dict) and "question" in item:
            questions.append(item["question"])
        else:
            raise ValueError(
                f"unrecognized entry in {questions_path}: {item!r} "
                '(expected a string or an object with a "question" key)'
            )
    return questions


def run_one_question(question: str) -> dict:
    """Call POST /api/ask for `question` and log the outcome.

    Never raises - a failed request is recorded with an "error" field
    instead of aborting the rest of the eval run.
    """
    started = time.perf_counter()
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/ask",
            json={"question": question},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        result = response.json()
        elapsed = time.perf_counter() - started
        return {
            "question": question,
            "answer": result.get("answer"),
            "reasoning_steps": len(result.get("reasoning_steps") or []),
            "contradiction_flagged": bool(result.get("contradictions")),
            "response_time_seconds": round(elapsed, 3),
        }
    except Exception as exc:  # noqa: BLE001 - one bad question must not stop the run
        elapsed = time.perf_counter() - started
        print(f"WARNING: request failed for question {question!r}: {exc}")
        return {
            "question": question,
            "answer": None,
            "reasoning_steps": None,
            "contradiction_flagged": None,
            "response_time_seconds": round(elapsed, 3),
            "error": str(exc),
        }


def print_summary(results: list[dict]) -> None:
    ok = [r for r in results if "error" not in r]
    failed = len(results) - len(ok)

    print("\n--- Eval summary ---")
    print(f"Total questions run: {len(results)}")
    if failed:
        print(f"Failed requests:     {failed}")

    if ok:
        avg_steps = sum(r["reasoning_steps"] for r in ok) / len(ok)
        avg_time = sum(r["response_time_seconds"] for r in ok) / len(ok)
        contradiction_count = sum(1 for r in ok if r["contradiction_flagged"])
        print(f"Average reasoning steps: {avg_steps:.2f}")
        print(f"Average response time:  {avg_time:.2f}s")
        print(f"Questions with a contradiction flagged: {contradiction_count}")
    else:
        print("No successful requests to summarize.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--questions-path",
        required=True,
        type=Path,
        help="Path to a JSON file of questions (array of strings or "
        '{"question": "..."} objects).',
    )
    args = parser.parse_args()

    questions_path: Path = args.questions_path
    if not questions_path.is_file():
        raise SystemExit(f"--questions-path is not a file: {questions_path}")

    try:
        questions = load_questions(questions_path)
    except (ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from None

    if not questions:
        raise SystemExit(f"{questions_path} contains no questions")

    results = [run_one_question(q) for q in questions]

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {len(results)} results to {RESULTS_PATH}")

    print_summary(results)


if __name__ == "__main__":
    main()
