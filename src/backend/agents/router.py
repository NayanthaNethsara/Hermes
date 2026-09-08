from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from src.backend.agents.service import (
    AgentRunRequest,
    AgentRunResponse,
    AgentService,
    AskRequest,
)
from src.backend.agents.sessions import delete_session, get_session, list_sessions

router = APIRouter(tags=["agents"])

STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Content-Type": "text/event-stream",
    "X-Accel-Buffering": "no",
}


@router.post("/agents/run", response_model=AgentRunResponse, summary="Ask a question")
@router.post("/agents/run/{track_id}", response_model=AgentRunResponse, include_in_schema=False)
async def run_agent(
    payload: AgentRunRequest,
    track_id: Optional[str] = None,
) -> AgentRunResponse:
    return await AgentService.run(
        query=payload.query,
        session_id=payload.session_id,
        max_iterations=payload.max_iterations,
    )


@router.post("/api/ask", response_model=AgentRunResponse, summary="Ask a question")
async def ask_endpoint(payload: AskRequest) -> AgentRunResponse:
    return await AgentService.run(
        query=payload.question,
        session_id=payload.session_id,
        max_iterations=payload.max_iterations,
    )


@router.post("/agents/stream", summary="Ask a question, streamed as SSE")
@router.post("/agents/stream/{track_id}", include_in_schema=False)
async def run_agent_stream(
    payload: AgentRunRequest,
    track_id: Optional[str] = None,
) -> StreamingResponse:
    return StreamingResponse(
        AgentService.stream(
            query=payload.query,
            session_id=payload.session_id,
            max_iterations=payload.max_iterations,
        ),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )


@router.post("/api/ask/stream", summary="Ask a question, streamed as SSE")
async def ask_stream_endpoint(payload: AskRequest) -> StreamingResponse:
    return StreamingResponse(
        AgentService.stream(
            query=payload.question,
            session_id=payload.session_id,
            max_iterations=payload.max_iterations,
        ),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )


@router.get("/api/sessions", summary="List sessions")
async def get_all_sessions() -> list[dict[str, Any]]:
    return await list_sessions()


@router.get("/api/sessions/{session_id}", summary="Get one session with its turns")
async def get_session_by_id(session_id: str) -> dict[str, Any]:
    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return session


@router.delete("/api/sessions/{session_id}", summary="Delete a session")
async def remove_session_by_id(session_id: str) -> dict[str, bool]:
    is_deleted = await delete_session(session_id)
    if not is_deleted:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return {"ok": True}
