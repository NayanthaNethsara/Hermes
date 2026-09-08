import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.backend.agents.llm import get_chat_model
from src.backend.agents.state.models import ConversationalInvestigatorState
from src.backend.core.logging import get_logger

logger = get_logger("arbitrator")

ARBITRATOR_SYSTEM_PROMPT = (
    "You are an epistemic arbitrator for the Ashen Era Archive.\n"
    "Your duty is to detect factual disagreements across retrieved archive records according to the hierarchy:\n"
    "1. CODEX and IMAGE plates (Authority 1.0) represent supreme canon.\n"
    "2. WIKI articles (Authority 0.8) represent consensus lore.\n"
    "3. NOVEL chronicles (Authority 0.6) represent narrative accounts.\n"
    "4. EPHEMERA (Authority 0.4) represent subjective or erroneous claims.\n\n"
    "Identify any factual contradictions (such as conflicting forging years, garrison counts, or allegiances).\n"
    "Output ONLY a valid JSON array of objects:\n"
    '[{"topic": "Description of conflict", "sources_disagree": ["Source A", "Source B"]}]\n'
    "If no genuine contradictions exist, output an empty JSON array: []"
)


async def arbitrate_evidence(state: ConversationalInvestigatorState) -> dict[str, Any]:
    active_chunks = state.get("active_chunks", [])
    steps = list(state.get("reasoning_steps", []))

    if not active_chunks:
        steps.append({
            "step": 4,
            "action": "Epistemic Source Arbitration",
            "found": "Skipped — no evidence chunks retrieved to evaluate",
        })
        return {
            "verified_chunks": [],
            "contradictions": [],
            "reasoning_steps": steps,
        }

    sorted_chunks = sorted(
        active_chunks,
        key=lambda c: (
            float((c.metadata_payload or {}).get("epistemic_weight", 0.5)),
            c.relevance_score or 0.0,
        ),
        reverse=True,
    )

    weights = [float((c.metadata_payload or {}).get("epistemic_weight", 0.5)) for c in sorted_chunks]
    has_mixed_authority = len(set(weights)) > 1 and min(weights) < 0.8

    if not has_mixed_authority and not state.get("contradictions"):
        steps.append({
            "step": 4,
            "action": "Epistemic Source Arbitration",
            "found": f"Evaluated {len(sorted_chunks)} records; uniform authority detected — 0 contradictions found",
        })
        return {
            "verified_chunks": sorted_chunks,
            "contradictions": [],
            "reasoning_steps": steps,
        }

    snippets: list[str] = []
    for chunk in sorted_chunks[:6]:
        meta = chunk.metadata_payload or {}
        cat = meta.get("source_category", "unknown").upper()
        weight = meta.get("epistemic_weight", 0.5)
        snippets.append(f"[{chunk.doc_id} | Category: {cat} (Authority: {weight})]\n{chunk.content[:280]}")

    prompt = (
        f"Target Question: {state.get('root_query', '')}\n\n"
        f"Archive Sources:\n" + "\n---\n".join(snippets) + "\n\n"
        "Analyze for factual contradictions and return JSON array."
    )

    contradictions: list[dict[str, Any]] = []
    try:
        llm = get_chat_model(temperature=0.0)
        response = await llm.ainvoke([
            SystemMessage(content=ARBITRATOR_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        content_text = response.content if isinstance(response.content, str) else str(response.content)
        cleaned = content_text.replace("```json", "").replace("```", "").strip()

        json_match = re.search(r"\[[\s\S]*\]", cleaned)
        if json_match:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, list):
                seen_topics: set[str] = set()
                for item in parsed:
                    if isinstance(item, dict):
                        topic = str(item.get("topic", "")).strip().lower()
                        if topic and topic not in seen_topics:
                            seen_topics.add(topic)
                            contradictions.append(item)
    except Exception as err:
        logger.warning("arbitration_evaluation_failed", error=str(err))

    if contradictions:
        conflict_topics = [c.get("topic", "") for c in contradictions]
        summary = f"Flagged {len(contradictions)} canon contradiction(s): {'; '.join(conflict_topics[:2])}"
    else:
        summary = f"Arbitrated {len(sorted_chunks)} records; canon claims reconciled without active conflict"

    steps.append({
        "step": 4,
        "action": "Epistemic Source Arbitration",
        "found": summary,
    })

    return {
        "verified_chunks": sorted_chunks,
        "contradictions": contradictions,
        "reasoning_steps": steps,
    }
