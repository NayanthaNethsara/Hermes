#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import glob
import json
from pathlib import Path
import re
import sys

DEFAULT_BRAIN_DIR = Path.home() / ".gemini" / "antigravity-ide" / "brain"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent


def find_latest_transcript(brain_dir: Path) -> Path | None:
    pattern = str(brain_dir / "*" / ".system_generated" / "logs" / "transcript_full.jsonl")
    matched_logs = glob.glob(pattern)
    if not matched_logs:
        return None
    return Path(max(matched_logs, key=lambda log_path: Path(log_path).stat().st_mtime))


def extract_dialogue(transcript_path: Path) -> list[str]:
    dialogue_blocks: list[str] = []
    with open(transcript_path, "r", encoding="utf-8") as file:
        for line in file:
            record = json.loads(line)
            step_type = record.get("type")
            content = record.get("content", "")

            if step_type == "USER_INPUT" and content:
                request_match = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", content, re.DOTALL)
                user_text = request_match.group(1).strip() if request_match else content.strip()
                if user_text:
                    dialogue_blocks.append(f"=== USER ===\n{user_text}\n\n")

            elif step_type == "PLANNER_RESPONSE" and content:
                assistant_text = content.strip()
                if assistant_text:
                    dialogue_blocks.append(f"=== ASSISTANT ===\n{assistant_text}\n\n")

    return dialogue_blocks


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Antigravity AI chat session into plain text.")
    parser.add_argument("--transcript", type=Path, help="Path to transcript_full.jsonl")
    parser.add_argument("--output", type=Path, help="Target path for output .txt file")
    args = parser.parse_args()

    transcript_file = args.transcript or find_latest_transcript(DEFAULT_BRAIN_DIR)
    if not transcript_file or not transcript_file.exists():
        sys.stderr.write(f"Error: No transcript found under {DEFAULT_BRAIN_DIR}\n")
        return 1

    dialogue_blocks = extract_dialogue(transcript_file)
    if not dialogue_blocks:
        sys.stderr.write(f"Warning: No messages found in {transcript_file}\n")
        return 1

    if args.output:
        destination_path = args.output
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        destination_path = DEFAULT_OUTPUT_DIR / f"chat_{timestamp}.txt"

    with open(destination_path, "w", encoding="utf-8") as out:
        out.write(f"Chat Transcript Export\n")
        out.write(f"Source: {transcript_file}\n")
        out.write(f"Exported At: {datetime.now().isoformat()}\n")
        out.write("=" * 60 + "\n\n")
        out.writelines(dialogue_blocks)

    print(f"Successfully exported {len(dialogue_blocks)} messages to {destination_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
