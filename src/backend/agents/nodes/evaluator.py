from typing import Any

from src.backend.agents.state.models import AgentState


async def evaluate_sufficiency(state: AgentState) -> dict[str, Any]:
    iteration = state.get("iteration_count", 0)
    max_iter = state.get("max_iterations", 3)
    chunks = state.get("retrieved_context", [])

    if iteration >= max_iter or len(chunks) >= 8:
        return {"is_sufficient": True}

    if not chunks:
        return {"is_sufficient": False}

    high_confidence_chunks = [c for c in chunks if c.relevance_score > 0.70]
    is_sufficient = len(high_confidence_chunks) >= 2 or iteration >= 2

    return {"is_sufficient": is_sufficient}
