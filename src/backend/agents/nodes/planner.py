import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.backend.agents.llm import get_chat_model
from src.backend.agents.state.models import ConversationalInvestigatorState
from src.backend.core.logging import get_logger

logger = get_logger("planner")

PLANNER_SYSTEM_PROMPT = (
    "You are a conversational query rewriter and search planner for the Ashen Era Archive.\n"
    "Your duty is to rewrite the latest question into a clear standalone retrieval query by resolving pronouns "
    "(such as 'it', 'they', 'he', 'that fortress', 'this relic') using the recent dialogue history.\n"
    "Output ONLY a valid JSON object matching this schema:\n"
    '{"rewritten_query": "string", "search_terms": ["string"]}\n'
    "Rules:\n"
    "- If the question is already clear and standalone, keep it unchanged in 'rewritten_query'.\n"
    "- 'search_terms' must contain 1-2 concise search queries optimized for keyword and vector search.\n"
    "- Do not answer the question."
)


async def plan_search_queries(state: ConversationalInvestigatorState) -> dict[str, Any]:
    root_query = state.get("root_query", "")
    messages = state.get("messages", [])

    steps = list(state.get("reasoning_steps", []))

    if len(messages) <= 1:
        steps.append({
            "step": len(steps) + 1,
            "action": "Contextual Query Planning",
            "found": f"Initial standalone research query planned: '{root_query}'",
        })
        return {
            "search_query": root_query,
            "planned_queries": [root_query] if root_query else [],
            "reasoning_steps": steps,
        }

    recent_history = messages[-4:-1] if len(messages) >= 4 else messages[:-1]
    history_lines: list[str] = []

    session_summary = state.get("session_summary")
    if session_summary:
        history_lines.append(f"Earlier Session Summary: {session_summary}")

    for msg in recent_history:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        history_lines.append(f"{role}: {content[:300]}")

    history_text = "\n".join(history_lines)
    user_prompt = (
        f"Conversation History:\n{history_text}\n\n"
        f"Latest Question: {root_query}\n\n"
        "Generate standalone query and search terms JSON."
    )

    rewritten_query = root_query
    planned_queries = [root_query]

    try:
        llm = get_chat_model(temperature=0.0)
        response = await llm.ainvoke([
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
        raw_text = response.content if isinstance(response.content, str) else str(response.content)
        cleaned = raw_text.replace("```json", "").replace("```", "").strip()

        json_match = re.search(r"\{[\s\S]*\}", cleaned)
        if json_match:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, dict):
                rewritten_query = parsed.get("rewritten_query", root_query).strip() or root_query
                search_terms = parsed.get("search_terms", [])
                if isinstance(search_terms, list) and search_terms:
                    planned_queries = [str(term).strip() for term in search_terms if str(term).strip()]
                else:
                    planned_queries = [rewritten_query]
    except Exception as error:
        logger.warning("planner_execution_fallback", error=str(error))

    queries_display = ", ".join(f"'{q}'" for q in planned_queries)
    steps.append({
        "step": len(steps) + 1,
        "action": "Contextual Query Planning",
        "found": f"Resolved conversational pronouns against dialogue history into: {queries_display}",
    })

    return {
        "search_query": rewritten_query,
        "planned_queries": planned_queries,
        "reasoning_steps": steps,
    }
