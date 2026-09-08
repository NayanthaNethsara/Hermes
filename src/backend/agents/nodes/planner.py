from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.backend.agents.llm import get_chat_model
from src.backend.agents.state.models import AgentState


async def plan_search_queries(state: AgentState) -> dict[str, Any]:
    root_query = state.get("root_query", "")
    iteration = state.get("iteration_count", 0)

    if iteration == 0:
        return {"search_queries": [root_query]}

    llm = get_chat_model(temperature=0.1)
    retrieved_snippets = [c.content[:200] for c in state.get("retrieved_context", [])]
    context_summary = "\n---\n".join(retrieved_snippets[-3:])

    prompt = f"""
Given the target question: "{root_query}"
And current retrieved context:
{context_summary}

Determine what information is still missing to give a conclusive answer.
Output up to 2 specific search queries to look up next, separated by newlines.
"""
    response = await llm.ainvoke([
        SystemMessage(content="You are an expert investigative search planner for the Ashen Era Archive."),
        HumanMessage(content=prompt),
    ])
    lines = [line.strip().lstrip("- ").lstrip("123456789. ") for line in response.content.split("\n") if line.strip()]
    return {"search_queries": lines[:2] or [root_query]}
