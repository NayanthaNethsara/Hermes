import json
from typing import Any, AsyncGenerator

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from src.backend.agents.graphs.workflow import get_compiled_graph
from src.backend.agents.sessions import upsert_session
from src.backend.core.config import get_settings
from src.backend.core.exceptions import (
    DEPENDENCY_UNAVAILABLE_MESSAGE,
    HermesException,
    is_connectivity_error,
    summarize_error,
)
from src.backend.core.logging import get_logger
from src.backend.retrieval.schemas import SearchResultChunk

logger = get_logger("agent_service")

STREAM_FAILURE_MESSAGE = "The research run failed before an answer could be produced."


def describe_stream_failure(error: Exception) -> dict[str, Any]:
    """Turn an exception into an SSE `error` payload the client can display."""
    if isinstance(error, HermesException):
        logger.warning(
            "graph_stream_known_failure",
            error=summarize_error(error),
        )
        message = error.message
    elif is_connectivity_error(error):
        logger.warning(
            "graph_stream_dependency_unavailable",
            error=summarize_error(error),
        )
        message = DEPENDENCY_UNAVAILABLE_MESSAGE
    else:
        logger.error("graph_stream_execution_error", error=summarize_error(error))
        message = STREAM_FAILURE_MESSAGE
    return {
        "error": message,
        "error_type": error.__class__.__name__,
        "detail": summarize_error(error),
    }


class AgentRunRequest(BaseModel):
    query: str
    session_id: str = "default"
    max_iterations: int = Field(default=5, ge=1, le=10)


class AgentRunResponse(BaseModel):
    answer: str
    referenced_figures: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_steps: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)


class AskRequest(BaseModel):
    question: str
    session_id: str = Field(default="default")
    max_iterations: int = Field(default=5, ge=1, le=10)


def format_sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def build_sources_payload(chunks: list[SearchResultChunk]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen_documents: set[str] = set()
    for chunk in chunks:
        if chunk.doc_id in seen_documents:
            continue
        seen_documents.add(chunk.doc_id)
        metadata = chunk.metadata_payload or {}
        category = metadata.get("source_category", "unknown")
        relevance = chunk.relevance_score or 0.0
        is_trusted = category in ["codex", "image"] or relevance > 0.7
        sources.append({
            "chunk_id": chunk.chunk_id,
            "title": chunk.doc_id,
            "section": metadata.get("section_title", "General Archive"),
            "category": category,
            "epistemic_weight": metadata.get("epistemic_weight", 0.5),
            "vector_score": round(chunk.vector_score, 4) if chunk.vector_score is not None else None,
            "keyword_score": round(chunk.keyword_score, 4) if chunk.keyword_score is not None else None,
            "relevance_score": round(relevance, 4),
            "figures": chunk.figure_references,
            "trust": "high" if is_trusted else "medium",
            "snippet": chunk.content[:300],
        })
    return sources


class AgentService:
    @classmethod
    async def run(
        cls,
        query: str,
        session_id: str = "default",
        max_iterations: int = 5,
    ) -> AgentRunResponse:
        graph = await get_compiled_graph()

        initial_state = {
            "root_query": query,
            "session_id": session_id,
            "max_iterations": min(max_iterations, get_settings().max_search_iterations),
            "messages": [HumanMessage(content=query)],
        }
        config = {"configurable": {"thread_id": session_id}}

        final_state = await graph.ainvoke(initial_state, config=config)

        verified_chunks = final_state.get("verified_chunks", [])
        sources = build_sources_payload(verified_chunks)
        referenced_figures = final_state.get("referenced_figures", [])
        citations = final_state.get("citations", [c.doc_id for c in verified_chunks])
        contradictions = final_state.get("contradictions", [])

        reasoning_steps = final_state.get("reasoning_steps", [])

        response = AgentRunResponse(
            answer=final_state.get("final_answer", ""),
            referenced_figures=referenced_figures,
            citations=citations,
            sources=sources,
            reasoning_steps=reasoning_steps,
            contradictions=contradictions,
        )
        await upsert_session(
            session_id=session_id,
            question=query,
            response_payload=response.model_dump(),
        )
        return response

    @classmethod
    async def stream(
        cls,
        query: str,
        session_id: str = "default",
        max_iterations: int = 5,
    ) -> AsyncGenerator[str, None]:
        try:
            graph = await get_compiled_graph()
        except Exception as error:
            yield format_sse_event("error", describe_stream_failure(error))
            return

        initial_state = {
            "root_query": query,
            "session_id": session_id,
            "max_iterations": min(max_iterations, get_settings().max_search_iterations),
            "messages": [HumanMessage(content=query)],
        }
        config = {"configurable": {"thread_id": session_id}}

        yield format_sse_event("status", {
            "stage": "starting",
            "message": "Initiating unified research graph...",
        })

        latest_sources: list[dict[str, Any]] = []
        latest_citations: list[str] = []
        latest_figures: list[str] = []
        latest_contradictions: list[dict[str, Any]] = []
        latest_reasoning_steps: list[dict[str, Any]] = []
        final_answer_text = ""
        current_node = ""

        try:
            async for event in graph.astream_events(initial_state, config=config, version="v2"):
                ev_type = event["event"]
                name = event.get("name", "")

                if ev_type == "on_chain_start":
                    if name in ["guardrail", "planner", "retriever", "critic", "arbitrator", "synthesizer"]:
                        current_node = name

                    if name == "guardrail":
                        yield format_sse_event("status", {
                            "stage": "guardrail",
                            "message": "Validating safety and input intent...",
                        })
                    elif name == "planner":
                        yield format_sse_event("status", {
                            "stage": "planning",
                            "message": "Contextualizing question and formulating search plan...",
                        })
                    elif name == "retriever":
                        yield format_sse_event("status", {
                            "stage": "retrieving",
                            "message": "Searching archive with hybrid vector search...",
                        })
                    elif name == "critic":
                        yield format_sse_event("status", {
                            "stage": "reviewing",
                            "message": "Reviewing whether the evidence answers the question...",
                        })
                    elif name == "arbitrator":
                        yield format_sse_event("status", {
                            "stage": "arbitrating",
                            "message": "Arbitrating claims across epistemic hierarchy...",
                        })
                    elif name == "synthesizer":
                        yield format_sse_event("status", {
                            "stage": "synthesizing",
                            "message": "Synthesizing answer from authoritative sources...",
                        })

                elif ev_type == "on_chain_end":
                    if name == current_node:
                        current_node = ""

                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict) and "reasoning_steps" in output:
                        latest_reasoning_steps = output["reasoning_steps"]

                    if name in ("planner", "critic"):
                        yield format_sse_event("metadata", {
                            "sources": latest_sources,
                            "referenced_figures": latest_figures,
                            "citations": latest_citations,
                            "contradictions": latest_contradictions,
                            "reasoning_steps": latest_reasoning_steps,
                        })

                    elif name == "retriever":
                        chunks = output.get("active_chunks", [])
                        latest_sources = build_sources_payload(chunks)
                        latest_figures = output.get("active_figures", [])
                        latest_citations = list(dict.fromkeys([c.doc_id for c in chunks]))

                        yield format_sse_event("metadata", {
                            "sources": latest_sources,
                            "referenced_figures": latest_figures,
                            "citations": latest_citations,
                            "contradictions": latest_contradictions,
                            "reasoning_steps": latest_reasoning_steps,
                        })

                    elif name == "arbitrator":
                        latest_contradictions = output.get("contradictions", [])
                        yield format_sse_event("metadata", {
                            "sources": latest_sources,
                            "referenced_figures": latest_figures,
                            "citations": latest_citations,
                            "contradictions": latest_contradictions,
                            "reasoning_steps": latest_reasoning_steps,
                        })

                    elif name == "synthesizer":
                        final_answer_text = output.get("final_answer", final_answer_text)
                        latest_figures = output.get("referenced_figures", latest_figures)
                        latest_citations = output.get("citations", latest_citations)
                        latest_contradictions = output.get("contradictions", latest_contradictions)
                        latest_reasoning_steps = output.get("reasoning_steps", latest_reasoning_steps)

                elif ev_type == "on_chat_model_stream" and current_node == "synthesizer":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk:
                        raw = chunk.content
                        token_str = (
                            "".join(p if isinstance(p, str) else p.get("text", "") for p in raw)
                            if isinstance(raw, list)
                            else str(raw)
                        )
                        if token_str:
                            final_answer_text += token_str
                            yield format_sse_event("token", {"delta": token_str})

        except Exception as error:
            yield format_sse_event("error", describe_stream_failure(error))
            return

        done_payload = {
            "answer": final_answer_text,
            "referenced_figures": latest_figures,
            "citations": latest_citations,
            "sources": latest_sources,
            "contradictions": latest_contradictions,
            "reasoning_steps": latest_reasoning_steps,
        }
        await upsert_session(
            session_id=session_id,
            question=query,
            response_payload=done_payload,
        )
        yield format_sse_event("done", done_payload)
