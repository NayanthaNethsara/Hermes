from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.backend.agents.llm import get_chat_model
from src.backend.agents.prompts import (
    ARCHIVIST_SYSTEM_INSTRUCTION,
    build_synthesis_context,
    build_synthesis_user_prompt,
)
from src.backend.agents.state.models import ConversationalInvestigatorState
from src.backend.core.logging import get_logger

logger = get_logger("synthesizer")


class StructuredSynthesisResult(BaseModel):
    answer: str = Field(description="Rich, factual answer formatted in Markdown.")
    referenced_figures: list[str] = Field(
        default_factory=list,
        description="List of asset URLs or figure paths referenced directly in the response.",
    )


async def synthesize_answer(state: ConversationalInvestigatorState) -> dict[str, Any]:
    root_query = state.get("root_query", "")
    chunks = state.get("verified_chunks") or state.get("active_chunks") or state.get("retrieved_context", [])
    figure_urls = state.get("active_figures") or state.get("figure_urls") or state.get("figures", [])
    existing_contradictions = state.get("contradictions", [])

    citations = list(dict.fromkeys([chunk.doc_id for chunk in chunks]))
    context_str = build_synthesis_context(chunks)
    figures_str = "\n".join(figure_urls) if figure_urls else "No extracted figures."

    if state.get("is_conversational"):
        user_prompt = (
            f"User Greeting/Inquiry: {root_query}\n\n"
            "Provide a brief, polite greeting as Hermes, the Ashen Era archive intelligence assistant. "
            "State that you are ready to investigate historical records, illustrations, threat classifications, "
            "and conflicting accounts across the realm."
        )
    else:
        user_prompt = build_synthesis_user_prompt(
            root_query=root_query,
            context_str=context_str,
            figures_str=figures_str,
        )

    llm = get_chat_model(temperature=0.1)

    accumulated_parts: list[str] = []
    try:
        async for chunk in llm.astream([
            SystemMessage(content=ARCHIVIST_SYSTEM_INSTRUCTION),
            HumanMessage(content=user_prompt),
        ]):
            raw_chunk = chunk.content
            chunk_str = (
                "".join(p if isinstance(p, str) else p.get("text", "") for p in raw_chunk)
                if isinstance(raw_chunk, list)
                else str(raw_chunk)
            )
            accumulated_parts.append(chunk_str)
        answer_text = "".join(accumulated_parts).strip()
    except Exception as error:
        logger.warning("synthesizer_invocation_fallback", error=str(error))
        answer_text = (
            f"Based on the archive evidence:\n\n"
            + "\n".join([f"- {c.content[:300]}..." for c in chunks[:3]])
        )

    embedded_figures = [
        fig for fig in figure_urls
        if Path(fig).name in answer_text or fig in answer_text
    ]
    actual_referenced_figures = embedded_figures if embedded_figures else figure_urls[:1]

    steps = list(state.get("reasoning_steps", []))
    if state.get("is_conversational"):
        syn_detail = "Formulated conversational greeting and capability overview as Hermes"
    else:
        cited_str = ", ".join(f"`{c}`" for c in citations[:3])
        syn_detail = f"Synthesized answer citing {len(citations)} authoritative source(s) [{cited_str}]"
        if actual_referenced_figures:
            syn_detail += f" with {len(actual_referenced_figures)} inline visual plate(s)"

    steps.append({
        "step": 5,
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
