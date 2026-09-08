import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.backend.agents.llm import get_chat_model
from src.backend.agents.state.models import ConversationalInvestigatorState
from src.backend.core.logging import get_logger

logger = get_logger("planner")

PLANNER_SYSTEM_PROMPT = (
    "You are a research query planner and analyzer for the Ashen Era Archive.\n"
    "Your duty is to analyze the research question, resolve any conversational references or pronouns "
    "using dialogue history, and formulate a targeted retrieval strategy.\n"
    "For compositional or multi-hop questions (such as 'Which war was won by the organization that included X?'), "
    "identify the primary pivot entity (e.g., X's organization or faction) that must be investigated first.\n"
    "Extract 1 to 2 targeted search queries optimized for hybrid keyword and dense vector retrieval. "
    "Strip conversational filler and question wrappers.\n"
    "Output ONLY a valid JSON object matching this schema:\n"
    '{"analysis": "string", "rewritten_query": "string", "search_terms": ["string"]}\n'
    "Rules:\n"
    "- 'analysis' briefly states the question's core subject or required investigative link.\n"
    "- 'rewritten_query' is the complete standalone question with all pronouns resolved.\n"
    "- 'search_terms' contains 1-2 concise, targeted queries naming the critical entities or facts.\n"
    "- Do not answer the question."
)


async def plan_search_queries(state: ConversationalInvestigatorState) -> dict[str, Any]:
    root_query = state.get("root_query", "")
    messages = state.get("messages", [])
    steps = list(state.get("reasoning_steps", []))

    history_lines: list[str] = []
    session_summary = state.get("session_summary")
    if session_summary:
        history_lines.append(f"Earlier Session Summary: {session_summary}")

    if len(messages) > 1:
        recent_history = messages[-4:-1] if len(messages) >= 4 else messages[:-1]
        for msg in recent_history:
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            history_lines.append(f"{role}: {content[:300]}")

    history_text = "\n".join(history_lines) if history_lines else "None (initial question)"
    user_prompt = (
        f"Conversation History:\n{history_text}\n\n"
        f"Target Question: {root_query}\n\n"
        "Analyze question structure, resolve references, and return JSON planning object."
    )

    analysis_text = ""
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
                analysis_text = str(parsed.get("analysis", "")).strip()
                rewritten_query = str(parsed.get("rewritten_query", root_query)).strip() or root_query
                search_terms = parsed.get("search_terms", [])
                if isinstance(search_terms, list) and search_terms:
                    extracted_terms = [str(term).strip() for term in search_terms if str(term).strip()]
                    if extracted_terms:
                        planned_queries = extracted_terms
    except Exception as error:
        logger.warning("planner_execution_fallback", error=str(error))

    queries_display = ", ".join(f"'{q}'" for q in planned_queries)
    planning_summary = (
        f"{analysis_text} Formulated retrieval queries: {queries_display}"
        if analysis_text
        else f"Planned targeted retrieval queries: {queries_display}"
    )

    steps.append({
        "step": len(steps) + 1,
        "action": "Contextual Query Planning",
        "found": planning_summary,
    })

    return {
        "search_query": rewritten_query,
        "planned_queries": planned_queries,
        "reasoning_steps": steps,
    }
