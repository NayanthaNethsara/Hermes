import re
from typing import Any

from src.backend.agents.state.models import ConversationalInvestigatorState

CONVERSATIONAL_PATTERNS = [
    r"^(hi|hello|hey|greetings|good\s+(morning|afternoon|evening))\b",
    r"^(who\s+are\s+you|what\s+is\s+your\s+name|what\s+can\s+you\s+do|help)\b",
    r"^(thanks|thank\s+you|bye|goodbye)\b",
]


async def guardrail_input(state: ConversationalInvestigatorState) -> dict[str, Any]:
    query = state.get("root_query", "").strip()
    if not query and state.get("messages"):
        last_message = state["messages"][-1]
        query = (
            last_message.content
            if isinstance(last_message.content, str)
            else str(last_message.content)
        ).strip()

    cleaned_query = query.lower()
    is_conversational = any(
        re.search(pattern, cleaned_query) for pattern in CONVERSATIONAL_PATTERNS
    )

    reasoning_step = {
        "step": 1,
        "action": "Input Guardrail & Intent Classification",
        "found": (
            "Conversational greeting or pleasantry detected — routing via zero-retrieval fast-path"
            if is_conversational
            else f"Historical archive research query validated: '{query}'"
        ),
    }

    return {
        "root_query": query,
        "search_query": query,
        "is_conversational": is_conversational,
        "iteration_count": 0,
        "is_sufficient": False,
        "knowledge_gap": "",
        "planned_queries": [],
        "searched_queries": [],
        "active_chunks": [],
        "active_figures": [],
        "verified_chunks": [],
        "contradictions": [],
        "retrieved_context": [],
        "figures": [],
        "figure_urls": [],
        "reasoning_steps": [reasoning_step],
    }
