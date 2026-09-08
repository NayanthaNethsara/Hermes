import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.backend.agents.llm import get_chat_model
from src.backend.agents.state.models import (
    ANSWERED,
    NOT_IN_ARCHIVE,
    SEARCH_AGAIN,
    VALID_VERDICTS,
    ConversationalInvestigatorState,
)
from src.backend.core.config import get_settings
from src.backend.core.logging import get_logger
from src.backend.retrieval.visuals import describe_available_figures

logger = get_logger("critic")

CRITIC_SYSTEM_PROMPT = (
    "You are a research critic for the Ashen Era Archive.\n"
    "You receive a question, the searches already run, and the evidence gathered so far. Decide "
    "whether the archive has yielded enough to answer.\n"
    "Output ONLY a valid JSON object matching this schema:\n"
    '{"verdict": "answered", "missing_information": "string", "next_queries": ["string"]}\n'
    "\n"
    "VERDICTS\n"
    '- "answered": the evidence answers the question in substance. Judge substance, not wording. '
    "A passage describing what a plate depicts answers a question about what that plate shows, "
    "even if it never uses the asker's exact term. Hedged or descriptive source wording still "
    "counts as an answer. Do not withhold this verdict over a synonym.\n"
    '- "search_again": a specific named fact is genuinely absent, and a differently worded search '
    "could plausibly find it.\n"
    '- "not_in_archive": the evidence is on topic but the archive does not appear to record this '
    "fact. Choose this over searching again when the last search added little or drifted off "
    "topic; a further search would only add noise.\n"
    "\n"
    "RULES\n"
    "- 'missing_information' names the absent fact for the two negative verdicts, and is an empty "
    "string for \"answered\".\n"
    "- 'next_queries' holds 1 or 2 searches for \"search_again\" only, each worded differently "
    "from the searches already run. It is an empty list for the other verdicts.\n"
    "- Do not answer the question yourself, and never require a source to repeat the question's "
    "phrasing.\n"
    "- The figure descriptions are the archive's own analysis of its plates. For a question about "
    "what an illustration shows or depicts, they are authoritative: if they record the detail, "
    'the verdict is "answered".'
)

EVIDENCE_PREVIEW_CHARS = 600
MAX_EVIDENCE_ITEMS = 6

NOISE_PREFIXES = ("**File**:", "**Asset Path**:", "**Source File**:")
NOISE_LINES = {
    "no inscribed text detected.",
    "no legible text found.",
    "no extracted figures.",
}


def condense_for_review(content: str) -> str:
    kept: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(NOISE_PREFIXES):
            continue
        if line.lower() in NOISE_LINES:
            continue
        line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line).strip()
        if not line:
            continue
        line = line.lstrip("#").strip()
        if line.startswith("Visual Asset:"):
            continue
        if line:
            kept.append(line)
    return " ".join(kept)


def build_evidence_digest(chunks: list[Any]) -> str:
    if not chunks:
        return "No evidence retrieved."
    lines: list[str] = []
    for chunk in chunks[:MAX_EVIDENCE_ITEMS]:
        metadata = chunk.metadata_payload or {}
        category = str(metadata.get("source_category", "unknown")).upper()
        body = condense_for_review(chunk.content)[:EVIDENCE_PREVIEW_CHARS]
        lines.append(f"[{chunk.doc_id} | {category}] {body}")
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
    last_hop_yield = state.get("last_hop_yield", len(chunks))
    prompt = (
        f"Question: {state.get('root_query', '')}\n\n"
        f"Search hops so far: {hops_used} of {max_hops} allowed\n"
        f"Searches already run: {', '.join(queries_run) if queries_run else 'none'}\n"
        f"New passages found by the most recent search: {last_hop_yield}\n\n"
        f"Evidence gathered ({len(chunks)} passage(s)):\n{build_evidence_digest(chunks)}\n\n"
        f"Figures in evidence:\n{describe_available_figures(state.get('active_figures', []))}\n\n"
        "Return the verdict JSON."
    )

    verdict = ANSWERED
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
                candidate = str(parsed.get("verdict", ANSWERED)).strip().lower()
                verdict = candidate if candidate in VALID_VERDICTS else ANSWERED
                knowledge_gap = str(parsed.get("missing_information", "")).strip()
                raw_queries = parsed.get("next_queries", [])
                if isinstance(raw_queries, list):
                    next_queries = [str(q).strip() for q in raw_queries if str(q).strip()][:2]
    except Exception as error:
        logger.warning("critic_evaluation_fallback", error=str(error))
        verdict = ANSWERED

    if verdict == SEARCH_AGAIN and not next_queries:
        verdict = NOT_IN_ARCHIVE
    if verdict == ANSWERED:
        knowledge_gap = ""
        next_queries = []

    if verdict == ANSWERED:
        detail = f"Evidence answers the question after {hops_used} hop(s) — no further search needed"
    elif verdict == NOT_IN_ARCHIVE:
        detail = (
            f"The archive does not appear to record {knowledge_gap or 'this detail'} — "
            "answering with what it does hold rather than searching further"
        )
    else:
        detail = f"Gap identified: {knowledge_gap or 'an unresolved detail'}. Searching again for: {', '.join(next_queries)}"

    steps.append({
        "step": len(steps) + 1,
        "action": "Sufficiency Review",
        "found": detail,
    })

    logger.info(
        "sufficiency_assessed",
        hop=hops_used,
        verdict=verdict,
        last_hop_yield=last_hop_yield,
        next_queries=next_queries,
    )

    return {
        "evidence_verdict": verdict,
        "knowledge_gap": knowledge_gap,
        "planned_queries": next_queries,
        "reasoning_steps": steps,
    }
