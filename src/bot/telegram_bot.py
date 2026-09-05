"""Telegram front-end for The Archivist.

Every text message a user sends is treated as a question: it's forwarded
to the local FastAPI backend's POST /api/ask, and the answer (plus up to
3 sources, and a contradiction note when relevant) is sent back as a
plain-text reply.

How to run it:
    1. The FastAPI backend (src/backend/main.py, Prompt 7) must already
       be running locally - this bot is a second doorway to it, it does
       not run the agent loop itself:
           uvicorn src.backend.main:app --reload
    2. Copy configuration-example/.env.example to .env at the repo root
       and fill in TELEGRAM_BOT_TOKEN.
    3. From the repo root:
           python -m src.bot.telegram_bot
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from telegram import Update  # noqa: E402
from telegram.ext import Application, ContextTypes, MessageHandler, filters  # noqa: E402

load_dotenv()

# Overridable for convenience, but defaults to exactly what the backend
# (src/backend/main.py) listens on locally.
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
MAX_SOURCES_SHOWN = 3
# The agent loop can take a while (up to 5 search hops), so give it room.
REQUEST_TIMEOUT_SECONDS = 90


def require_telegram_token() -> str:
    """Fetch TELEGRAM_BOT_TOKEN or fail fast with a clear message."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set - copy "
            "configuration-example/.env.example to .env at the repo root "
            "and fill it in"
        )
    return token


def ask_backend(question: str) -> dict:
    """POST `question` to the local backend's /api/ask and return its JSON
    response (see docs/architecture.md section 6 for the shape)."""
    response = requests.post(
        f"{BACKEND_URL}/api/ask",
        json={"question": question},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def format_reply(result: dict) -> str:
    """Turn an /api/ask response into the plain-text Telegram reply."""
    lines: list[str] = []

    for contradiction in result.get("contradictions") or []:
        lines.append(f"⚠️ Note: sources disagree on: {contradiction['topic']}")

    lines.append(result.get("answer", ""))

    sources = result.get("sources") or []
    if sources:
        lines.append("")
        lines.append("Sources:")
        for source in sources[:MAX_SOURCES_SHOWN]:
            lines.append(f"{source['title']} [{source['trust']}]")

    return "\n".join(lines)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Treat any text message as a question for the archive."""
    message = update.message
    if message is None or not message.text:
        return

    try:
        # ask_backend() is blocking and can take a long time (the agent
        # loop runs up to 5 search hops). Run it off the event loop so
        # the bot stays responsive to other users while it waits.
        result = await asyncio.to_thread(ask_backend, message.text)
        reply = format_reply(result)
    except Exception as exc:  # noqa: BLE001 - a failed request must not crash the bot
        print(f"WARNING: backend request failed: {exc}")
        reply = "Something went wrong, try again."

    await message.reply_text(reply)


def main() -> None:
    # Answers/errors echoed to the console can contain non-ASCII text; on
    # a Windows console (cp1252) printing those raises UnicodeEncodeError
    # and would take the bot down. Degrade to "?" instead.
    sys.stdout.reconfigure(errors="replace")

    token = require_telegram_token()

    application = Application.builder().token(token).build()
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    print("The Archivist Telegram bot is running (long-polling)...")
    application.run_polling()


if __name__ == "__main__":
    main()
