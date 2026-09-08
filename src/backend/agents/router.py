from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.backend.agents.graphs.investigator_1c import build_investigator_1c_graph
from src.backend.agents.graphs.multimodal_1a import build_multimodal_1a_graph
from src.backend.agents.state.base import create_initial_state

router = APIRouter(tags=["agents"])


class AgentRunRequest(BaseModel):
    query: str
    max_iterations: int = Field(default=5, ge=1, le=10)


class AgentRunResponse(BaseModel):
    answer: str
    referenced_figures: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    iteration_count: int = 0
    sources: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_steps: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)


class AskRequest(BaseModel):
    question: str


@router.post("/agents/run/{track_id}", response_model=AgentRunResponse)
async def run_agent_track(
    track_id: str,
    payload: AgentRunRequest,
) -> AgentRunResponse:
    track_normalized = track_id.lower().replace("-", "_").replace("track_", "").strip()

    if track_normalized in ["1a", "multimodal", "multimodal_1a"]:
        graph = build_multimodal_1a_graph()
    elif track_normalized in ["1c", "investigator", "investigator_1c"]:
        graph = build_investigator_1c_graph()
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown track '{track_id}'. Available: '1a' (multimodal) or '1c' (investigator)",
        )

    initial_state = create_initial_state(
        query=payload.query,
        max_iterations=payload.max_iterations,
    )

    final_state = await graph.ainvoke(initial_state)

    sources_list: list[dict[str, Any]] = []
    for chunk in final_state.get("retrieved_context", []):
        meta = chunk.metadata_payload or {}
        cat = meta.get("source_category", "unknown")
        sources_list.append({
            "chunk_id": chunk.chunk_id,
            "title": chunk.doc_id,
            "section": meta.get("section_title", "General"),
            "category": cat,
            "epistemic_weight": meta.get("epistemic_weight", 0.5),
            "vector_score": round(chunk.vector_score, 4) if chunk.vector_score is not None else None,
            "keyword_score": round(chunk.keyword_score, 4) if chunk.keyword_score is not None else None,
            "relevance_score": round(chunk.relevance_score, 4),
            "figures": chunk.figure_references,
            "trust": "high" if cat in ["codex", "image"] or chunk.relevance_score > 0.7 else "medium",
            "snippet": chunk.content[:300],
        })

    reasoning_steps = [
        {"step": 1, "action": "Hybrid vector and keyword search", "found": f"{len(final_state.get('retrieved_context', []))} chunks"},
        {"step": 2, "action": "Multimodal figure linking", "found": f"{len(final_state.get('referenced_figures', []))} figures"},
    ]

    return AgentRunResponse(
        answer=final_state.get("final_answer", ""),
        referenced_figures=final_state.get("referenced_figures", []),
        citations=final_state.get("citations", []),
        iteration_count=final_state.get("iteration_count", 1),
        sources=sources_list,
        reasoning_steps=reasoning_steps,
        contradictions=final_state.get("contradictions", []),
    )


@router.post("/api/ask", response_model=AgentRunResponse)
async def ask_endpoint(payload: AskRequest) -> AgentRunResponse:
    request = AgentRunRequest(query=payload.question)
    return await run_agent_track(track_id="1a", payload=request)
