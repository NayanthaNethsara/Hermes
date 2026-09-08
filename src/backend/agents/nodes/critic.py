import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.backend.agents.llm import get_chat_model
from src.backend.agents.state.models import ConversationalInvestigatorState
from src.backend.core.config import get_settings
from src.backend.core.logging import get_logger

logger = get_logger("critic")

CRITIC_SYSTEM_PROMPT = (
    "You are a research critic for the Ashen Era Archive.\n"
    "You receive a question and the evidence gathered so far. Decide whether that evidence answers "
    "the question completely.\n"
    "Output ONLY a valid JSON object matching this schema:\n"
    '{"is_sufficient": true, "missing_information": "string", "next_queries": ["string"]}\n'
    "Rules:\n"
    "- Set 'is_sufficient' to true only when every part of the question can be answered from the evidence shown.\n"
    "- When it is false, 'missing_information' names the specific fact that is still absent.\n"
    "- 'next_queries' holds 1 or 2 searches aimed at that missing fact, worded differently from the "
    "searches already run.\n"
    "- When it is true, 'missing_information' is an empty string and 'next_queries' is an empty list.\n"
    "- Judge only coverage of the question. Do not answer it."
)

EVIDENCE_PREVIEW_CHARS = 220
MAX_EVIDENCE_ITEMS = 8


def build_evidence_digest(chunks: list[Any]) -> str:
    if not chunks:
        return "No evidence retrieved."
    lines: list[str] = []
    for chunk in chunks[:MAX_EVIDENCE_ITEMS]:
        metadata = chunk.metadata_payload or {}
        category = str(metadata.get("source_category", "unknown")).upper()
        lines.append(f"[{chunk.doc_id} | {category}] {chunk.content[:EVIDENCE_PREVIEW_CHARS]}")
    return "\n".join(lines)


async def assess_sufficiency(state: ConversationalInvestigatorState) -> dict[str, Any]:
    steps = list(state.get("reasoning_steps", []))
    chunks = state.get("active_chunks", [])
    hops_used = state.get("iteration_count", 0)
    max_hops = state.get("max_iterations") or get_settings().max_search_iterations

    if hops_used >= max_hops:
        steps.append({
            "step": len(steps) + 1,
            "action": "Sufficiency Review",
            "found": f"Search budget of {max_hops} hop(s) reached — answering with the evidence in hand",
        })
        return {"reasoning_steps": steps}

    queries_run = state.get("searched_queries", [])
    prompt = (
        f"Question: {state.get('root_query', '')}\n\n"
        f"Searches already run: {', '.join(queries_run) if queries_run else 'none'}\n\n"
        f"Evidence gathered ({len(chunks)} passage(s)):\n{build_evidence_digest(chunks)}\n\n"
        "Return the sufficiency JSON."
    )

    is_sufficient = True
    knowledge_gap = ""
    next_queries: list[str] = []

    try:
        llm = get_chat_model(temperature=0.0)
        response = await llm.ainvoke([
            SystemMessage(content=CRITIC_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        raw_text = response.content if isinstance(response.content, str) else str(response.content)
        cleaned = raw_text.replace("```json", "").replace("```", "").strip()

        json_match = re.search(r"\{[\s\S]*\}", cleaned)
        if json_match:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, dict):
                is_sufficient = bool(parsed.get("is_sufficient", True))
                knowledge_gap = str(parsed.get("missing_information", "")).strip()
                raw_queries = parsed.get("next_queries", [])
                if isinstance(raw_queries, list):
                    next_queries = [str(q).strip() for q in raw_queries if str(q).strip()][:2]
    except Exception as error:
        logger.warning("critic_evaluation_fallback", error=str(error))

    if not next_queries:
        is_sufficient = True
        knowledge_gap = ""

    if is_sufficient:
        detail = f"Evidence covers the question after {hops_used} hop(s) — no further search needed"
    else:
        gap_text = knowledge_gap or "an unresolved detail"
        detail = f"Gap identified: {gap_text}. Searching again for: {', '.join(next_queries)}"

    steps.append({
        "step": len(steps) + 1,
        "action": "Sufficiency Review",
        "found": detail,
    })

    logger.info(
        "sufficiency_assessed",
        hop=hops_used,
        is_sufficient=is_sufficient,
        next_queries=next_queries,
    )

    return {
        "is_sufficient": is_sufficient,
        "knowledge_gap": knowledge_gap,
        "planned_queries": next_queries,
        "reasoning_steps": steps,
    }
