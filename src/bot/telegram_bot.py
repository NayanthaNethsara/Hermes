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
from telegram.ext import (  # noqa: E402
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

# Overridable for convenience, but defaults to exactly what the backend
# (src/backend/main.py) listens on locally.
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
MAX_SOURCES_SHOWN = 3
# The agent loop can take a while. A measured question at stock settings took
# ~110s, which silently blew the previous 90s timeout and surfaced in Telegram
# as "Something went wrong, try again" - the bot looked broken while the
# backend was working fine and about to answer. Set well above the worst case
# rather than near it; the backend's own per-call timeouts bound the total.
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("BOT_REQUEST_TIMEOUT_SECONDS", "300"))


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


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Answer /start.

    Telegram shows a Start button on first contact, which sends /start. The
    bot previously filtered commands out entirely and replied to nothing,
    so a new user's first interaction was silence - it looked broken.
    """
    if update.message is None:
        return
    await update.message.reply_text(
        "I'm The Archivist. Ask me a question about the Ashen Era Archive and "
        "I'll search it, weigh how much each source can be trusted, and tell "
        "you when sources disagree.\n\n"
        "Answers take up to a couple of minutes - I search several times "
        "before replying.\n\n"
        "Try: Which war was won by the organization that included Isolde "
        "Mournvale as one of its members?"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Treat any text message as a question for the archive."""
    message = update.message
    if message is None or not message.text:
        return

    # A question takes 45s-2min. Without an immediate acknowledgement the
    # chat sits silent and looks dead, so say something first and keep the
    # "typing" indicator alive while the backend works.
    await message.reply_text("Searching the archive, one moment...")
    await message.chat.send_action("typing")

    try:
        # ask_backend() is blocking and can take a long time (the agent
        # loop runs several search hops). Run it off the event loop so
        # the bot stays responsive to other users while it waits.
        result = await asyncio.to_thread(ask_backend, message.text)
        reply = format_reply(result)
    except requests.exceptions.Timeout:
        print(f"WARNING: backend timed out after {REQUEST_TIMEOUT_SECONDS}s")
        reply = (
            f"That took longer than {REQUEST_TIMEOUT_SECONDS}s and I gave up "
            "waiting. The backend may still be working - try again, or lower "
            "MAX_SEARCH_HOPS in .env to make answers faster."
        )
    except requests.exceptions.ConnectionError:
        print(f"WARNING: could not reach the backend at {BACKEND_URL}")
        reply = (
            f"I can't reach the backend at {BACKEND_URL}. Make sure it's "
            "running: uvicorn src.backend.main:app"
        )
    except Exception as exc:  # noqa: BLE001 - a failed request must not crash the bot
        print(f"WARNING: backend request failed: {exc}")
        reply = f"Something went wrong: {exc}"

    await message.reply_text(reply)


def main() -> None:
    # Answers/errors echoed to the console can contain non-ASCII text; on
    # a Windows console (cp1252) printing those raises UnicodeEncodeError
    # and would take the bot down. Degrade to "?" instead.
    sys.stdout.reconfigure(errors="replace")

    token = require_telegram_token()

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    print("The Archivist Telegram bot is running (long-polling)...")
    application.run_polling()


if __name__ == "__main__":
    main()
