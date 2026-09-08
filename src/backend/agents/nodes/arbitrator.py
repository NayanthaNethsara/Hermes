import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.backend.agents.llm import get_chat_model
from src.backend.agents.prompts import build_arbitration_snippets
from src.backend.agents.state.models import ConversationalInvestigatorState
from src.backend.core.config import get_settings
from src.backend.core.logging import get_logger
from src.backend.retrieval.reranker import CrossEncoderReranker
from src.backend.retrieval.schemas import SearchResultChunk

logger = get_logger("arbitrator")

ARBITRATOR_SYSTEM_PROMPT = (
    "You are an epistemic arbitrator for the Ashen Era Archive.\n"
    "You detect places where two retrieved records make incompatible claims about the same fact.\n"
    "The authority hierarchy is:\n"
    "1. CODEX and IMAGE plates (Authority 1.0) are canon.\n"
    "2. WIKI articles (Authority 0.8) are consensus lore.\n"
    "3. NOVEL chronicles (Authority 0.6) are narrative accounts.\n"
    "4. EPHEMERA (Authority 0.4) are subjective claims.\n"
    "\n"
    "A contradiction requires BOTH sources to state something explicit about the same fact, and "
    "for those two statements to be impossible to reconcile: two different years for one event, "
    "two different counts for one garrison, two different holders of one title.\n"
    "\n"
    "The following are NOT contradictions. Never report them:\n"
    "- When the question asks what an official illustration, plate, or figure depicts, the visual record of that plate is authoritative; narrative prose describing the object elsewhere does not contradict what the illustration depicts.\n"
    "- One source is silent on what another describes. Absence is not disagreement (e.g., absence of a maker's stamp or forge mark does not contradict decorative engravings or motifs).\n"
    "- One source gives more or less detail than another.\n"
    "- Two sources describe different subjects, different moments, or different aspects.\n"
    "- A source hedges its own wording, or two sources use different words for the same thing.\n"
    "- Names differ. Document identifiers, file names, article slugs and plate titles are "
    "cataloguing labels, not claims the archive makes. A plate titled one way and an article "
    "titled another is not a disagreement about anything.\n"
    "- The dispute would be about naming or labelling rather than a fact of the world.\n"
    "\n"
    "Report nothing unless you can name both conflicting claims. When in doubt, report nothing.\n"
    "Output ONLY a valid JSON object matching this schema:\n"
    '{"analysis": "At most 1 concise sentence (under 25 words) comparing claims", "contradictions": [{"topic": "The fact in dispute", "sources_disagree": ["doc_a", "doc_b"]}]}\n'
    "If no genuine contradiction exists, \"contradictions\" must be an empty array: []"
)


async def consolidate_multi_hop_evidence(
    root_query: str,
    chunks: list[SearchResultChunk],
    limit: int,
) -> list[SearchResultChunk]:
    try:
        reranker = CrossEncoderReranker(min_score=0.0)
        return await reranker.rerank(query=root_query, candidates=chunks, top_k=limit)
    except Exception as error:
        logger.warning("cross_hop_consolidation_fallback", error=str(error))
        return chunks[:limit]


async def arbitrate_evidence(state: ConversationalInvestigatorState) -> dict[str, Any]:
    active_chunks = state.get("active_chunks", [])
    steps = list(state.get("reasoning_steps", []))

    if not active_chunks:
        steps.append({
            "step": len(steps) + 1,
            "action": "Epistemic Source Arbitration",
            "found": "Skipped — no evidence chunks retrieved to evaluate",
        })
        return {
            "verified_chunks": [],
            "contradictions": [],
            "reasoning_steps": steps,
        }

    consolidated_figures: list[str] | None = None
    context_limit = get_settings().synthesis_context_limit
    if len(active_chunks) > context_limit:
        gathered_count = len(active_chunks)
        active_chunks = await consolidate_multi_hop_evidence(
            root_query=state.get("root_query", ""),
            chunks=active_chunks,
            limit=context_limit,
        )
        consolidated_figures = list(
            dict.fromkeys(fig for chunk in active_chunks for fig in chunk.figure_references)
        )
        steps.append({
            "step": len(steps) + 1,
            "action": "Evidence Consolidation",
            "found": (
                f"Ranked {gathered_count} passage(s) gathered across hops against the original "
                f"question and kept the top {len(active_chunks)}"
            ),
        })

    sorted_chunks = sorted(
        active_chunks,
        key=lambda c: (
            float((c.metadata_payload or {}).get("epistemic_weight", 0.5)),
            c.relevance_score or 0.0,
        ),
        reverse=True,
    )

    figures_update = (
        {"active_figures": consolidated_figures} if consolidated_figures is not None else {}
    )

    distinct_docs = list(dict.fromkeys([c.doc_id for c in sorted_chunks]))
    if len(distinct_docs) < 2 and not state.get("contradictions"):
        steps.append({
            "step": len(steps) + 1,
            "action": "Epistemic Source Arbitration",
            "found": f"Evaluated {len(sorted_chunks)} record(s) from a single source [{distinct_docs[0] if distinct_docs else 'none'}] — 0 contradictions possible",
        })
        return {
            "verified_chunks": sorted_chunks,
            "contradictions": [],
            "reasoning_steps": steps,
            **figures_update,
        }

    prompt = (
        f"Target Question: {state.get('root_query', '')}\n\n"
        f"Archive Sources:\n{build_arbitration_snippets(sorted_chunks)}\n\n"
        "Analyze for factual contradictions and return the JSON object."
    )

    analysis_text = ""
    contradictions: list[dict[str, Any]] = []
    try:
        llm = get_chat_model(temperature=0.0)
        response = await llm.ainvoke([
            SystemMessage(content=ARBITRATOR_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        content_text = response.content if isinstance(response.content, str) else str(response.content)
        cleaned = content_text.replace("```json", "").replace("```", "").strip()

        raw_items: list[Any] = []
        obj_match = re.search(r"\{[\s\S]*\}", cleaned)
        if obj_match:
            parsed = json.loads(obj_match.group(0))
            if isinstance(parsed, dict):
                analysis_text = str(parsed.get("analysis", "")).strip()
                cand_list = parsed.get("contradictions", [])
                if isinstance(cand_list, list):
                    raw_items = cand_list
        else:
            arr_match = re.search(r"\[[\s\S]*\]", cleaned)
            if arr_match:
                parsed = json.loads(arr_match.group(0))
                if isinstance(parsed, list):
                    raw_items = parsed

        seen_topics: set[str] = set()
        for item in raw_items:
            if isinstance(item, dict):
                topic = str(item.get("topic", "")).strip().lower()
                if topic and topic not in seen_topics:
                    seen_topics.add(topic)
                    raw_sources = item.get("sources_disagree", [])
                    cleaned_sources = [
                        str(s).split("|")[0].strip()
                        for s in raw_sources
                        if str(s).strip()
                    ]
                    item["sources_disagree"] = cleaned_sources
                    contradictions.append(item)
    except Exception as err:
        logger.warning("arbitration_evaluation_failed", error=str(err))

    if contradictions:
        conflict_topics = [c.get("topic", "") for c in contradictions]
        summary = f"Flagged {len(contradictions)} canon contradiction(s): {'; '.join(conflict_topics[:2])}"
    else:
        summary = f"Arbitrated {len(sorted_chunks)} records across {len(distinct_docs)} source(s); canon claims reconciled without active conflict"

    steps.append({
        "step": len(steps) + 1,
        "action": "Epistemic Source Arbitration",
        "found": summary,
    })

    return {
        "verified_chunks": sorted_chunks,
        "contradictions": contradictions,
        "reasoning_steps": steps,
        **figures_update,
    }
