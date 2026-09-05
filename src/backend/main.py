"""FastAPI backend for The Archivist.

Exposes:
    POST /api/ask     {"question": "..."} -> orchestrator.run_archivist(question)
    GET  /api/health  -> {"status": "ok"}

Run it (from the repo root, with .env filled in):
    uvicorn src.backend.main:app --reload
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from src.backend.orchestrator import run_archivist  # noqa: E402

load_dotenv()

app = FastAPI(title="The Archivist")

# Hackathon demo: the frontend runs on a different port during development,
# so CORS is wide open. No auth or rate limiting - not needed for this demo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str


@app.post("/api/ask")
def ask(request: AskRequest) -> dict:
    """Run the full agent loop for `question` and return the answer.

    Deliberately a sync `def`, not `async def`: run_archivist() blocks for
    many seconds (up to 5 search hops of LLM calls). A sync endpoint is
    handed to FastAPI's threadpool, so one in-flight question can't freeze
    the whole event loop - /api/health and a second question still work.

    A demo crash is worse than a graceful error, so any failure here
    (missing API key, upstream API error, etc.) is caught and returned
    as a clear JSON error with HTTP 500 instead of raising.
    """
    try:
        return run_archivist(request.question)
    except Exception as exc:  # noqa: BLE001 - convert any failure to a clean 500
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
