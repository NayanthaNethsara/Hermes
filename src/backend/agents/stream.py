from typing import Any, AsyncGenerator

from src.backend.agents.service import AgentService, format_sse_event


async def stream_agent(
    query: str,
    max_iterations: int = 5,
    session_id: str = "default",
) -> AsyncGenerator[str, None]:
    async for sse_block in AgentService.stream(
        query=query,
        session_id=session_id,
        max_iterations=max_iterations,
    ):
        yield sse_block


async def stream_agent_track(
    track_id: str = "unified",
    query: str = "",
    max_iterations: int = 5,
    session_id: str = "default",
) -> AsyncGenerator[str, None]:
    async for sse_block in AgentService.stream(
        query=query,
        session_id=session_id,
        max_iterations=max_iterations,
    ):
        yield sse_block


__all__ = ["stream_agent", "stream_agent_track", "format_sse_event"]
