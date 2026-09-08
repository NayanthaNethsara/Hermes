import re
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.backend.agents.llm import get_chat_model
from src.backend.agents.prompts import (
    HERMES_SYSTEM_INSTRUCTION,
    build_greeting_user_prompt,
    build_synthesis_context,
    build_synthesis_user_prompt,
)
from src.backend.agents.state.models import ANSWERED, ConversationalInvestigatorState
from src.backend.core.logging import get_logger
from src.backend.retrieval.visuals import asset_url, describe_available_figures

logger = get_logger("synthesizer")


IMAGE_LINE_PATTERN = re.compile(r"!\[([^\]]*)\]\([^)]*\)")


def normalize_caption(text: str) -> str:
    return text.strip().rstrip(".").strip().lower()


def strip_caption_echo(answer: str) -> str:
    cleaned: list[str] = []
    pending_caption = ""
    for line in answer.splitlines():
        stripped = line.strip()
        match = IMAGE_LINE_PATTERN.fullmatch(stripped)
        if match:
            pending_caption = normalize_caption(match.group(1))
            cleaned.append(line)
            continue
        if pending_caption and normalize_caption(stripped) == pending_caption:
            pending_caption = ""
            continue
        if stripped:
            pending_caption = ""
        cleaned.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip()


async def synthesize_answer(state: ConversationalInvestigatorState) -> dict[str, Any]:
    root_query = state.get("root_query", "")
    chunks = state.get("verified_chunks") or state.get("active_chunks") or state.get("retrieved_context", [])
    figure_urls = state.get("active_figures") or state.get("figure_urls") or state.get("figures", [])
    existing_contradictions = state.get("contradictions", [])
    unresolved_gap = (
        "" if state.get("evidence_verdict") == ANSWERED else state.get("knowledge_gap", "")
    )

    citations = list(dict.fromkeys([chunk.doc_id for chunk in chunks]))
    context_str = build_synthesis_context(chunks)
    figures_str = describe_available_figures(figure_urls)

    if state.get("is_conversational"):
        user_prompt = build_greeting_user_prompt(root_query)
    else:
        user_prompt = build_synthesis_user_prompt(
            root_query=root_query,
            context_str=context_str,
            figures_str=figures_str,
            knowledge_gap=unresolved_gap,
        )

    llm = get_chat_model(temperature=0.0)

    accumulated_parts: list[str] = []
    try:
        async for chunk in llm.astream([
            SystemMessage(content=HERMES_SYSTEM_INSTRUCTION),
            HumanMessage(content=user_prompt),
        ]):
            raw_chunk = chunk.content
            chunk_str = (
                "".join(p if isinstance(p, str) else p.get("text", "") for p in raw_chunk)
                if isinstance(raw_chunk, list)
                else str(raw_chunk)
            )
            accumulated_parts.append(chunk_str)
    except Exception as error:
        logger.error(
            "synthesizer_generation_failed",
            error_type=type(error).__name__,
            error_detail=str(error),
        )

    answer_text = strip_caption_echo("".join(accumulated_parts))
    if not answer_text:
        answer_text = (
            "I could not generate an answer for this question just now. "
            f"The archive returned {len(chunks)} relevant passage(s), listed as sources below. "
            "Please try again."
        )

    actual_referenced_figures = [
        fig for fig in figure_urls
        if Path(fig).name in answer_text or fig in answer_text or asset_url(fig) in answer_text
    ]

    steps = list(state.get("reasoning_steps", []))
    if state.get("is_conversational"):
        syn_detail = "Formulated conversational greeting and capability overview as Hermes"
    else:
        cited_str = ", ".join(f"`{c}`" for c in citations[:3])
        syn_detail = f"Synthesized answer citing {len(citations)} authoritative source(s) [{cited_str}]"
        if actual_referenced_figures:
            syn_detail += f" with {len(actual_referenced_figures)} of {len(figure_urls)} available plate(s) embedded"
        elif figure_urls:
            syn_detail += f"; none of the {len(figure_urls)} available plate(s) supported the answer"
        if unresolved_gap:
            syn_detail += f"; disclosed unresolved gap: {unresolved_gap}"

    steps.append({
        "step": len(steps) + 1,
        "action": "Evidence Synthesis",
        "found": syn_detail,
    })

    return {
        "final_answer": answer_text,
        "answer": answer_text,
        "referenced_figures": actual_referenced_figures,
        "citations": citations,
        "contradictions": existing_contradictions,
        "messages": [AIMessage(content=answer_text)],
        "active_chunks": [],
        "reasoning_steps": steps,
    }
