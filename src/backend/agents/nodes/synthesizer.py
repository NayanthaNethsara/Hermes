import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.backend.agents.llm import get_chat_model
from src.backend.agents.state.models import AgentState
from src.backend.core.logging import get_logger

logger = get_logger("synthesizer")


class SynthesizerOutput(BaseModel):
    answer: str = Field(description="Clear, comprehensive factual answer to the question.")
    referenced_figures: list[str] = Field(
        default_factory=list,
        description="List of asset URLs or figure paths referenced directly in the response.",
    )
    citations: list[str] = Field(
        default_factory=list,
        description="Source documents or codex entries cited.",
    )


async def synthesize_answer(state: AgentState) -> dict[str, Any]:
    root_query = state.get("root_query", "")
    chunks = state.get("retrieved_context", [])
    figure_urls = state.get("figure_urls", [])

    context_blocks: list[str] = []
    citations: list[str] = []
    for index, chunk in enumerate(chunks):
        doc_id = chunk.doc_id
        citations.append(doc_id)
        payload = chunk.metadata_payload or {}
        category = payload.get("source_category", "archive").upper()
        weight = float(payload.get("epistemic_weight", 1.0))
        context_blocks.append(
            f"[Source {index + 1}: {doc_id} | Category: {category} (Authority: {weight:.1f})]\n{chunk.content}"
        )

    context_str = "\n\n---\n\n".join(context_blocks)
    figures_str = "\n".join(figure_urls) if figure_urls else "No extracted figures."

    system_instruction = (
        "You are the Archivist AI, an expert technical and historical assistant for the Ashen Era Archive.\n"
        "Your task is to provide rich, accurate answers strictly grounded in the provided document evidence.\n"
        "Adhere strictly to the epistemic authority hierarchy:\n"
        "- CODEX and IMAGE plates represent supreme canon (official threat ratings, gauges, attunement costs, garrisons).\n"
        "- WIKI records provide consensus lore and registry overviews.\n"
        "- NOVEL chronicles provide narrative perspectives.\n"
        "- EPHEMERA records (letters, trial transcripts, ballads) are subjective claims.\n"
        "If sources conflict on a fact (e.g. year, victor, or count), uphold the higher-tier source as canon and report the disagreement.\n"
        "If a diagram, figure, or table asset is available, mention and embed it directly.\n"
        "Output ONLY a valid JSON object matching this schema:\n"
        '{"answer": "string", "referenced_figures": ["string"], "citations": ["string"], "contradictions": [{"topic": "string", "sources_disagree": ["string"]}]}'
    )

    user_prompt = (
        f"Question: {root_query}\n\n"
        f"Available Visual Assets:\n{figures_str}\n\n"
        f"Evidence Chunks:\n{context_str}\n\n"
        "Synthesize a rich answer embedding relevant figures if applicable."
    )

    llm = get_chat_model(temperature=0.1)
    content_text = ""
    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_instruction),
            HumanMessage(content=user_prompt),
        ])
        raw_content = response.content
        if isinstance(raw_content, list):
            content_text = "".join(part if isinstance(part, str) else part.get("text", "") for part in raw_content).strip()
        else:
            content_text = str(raw_content).strip()

        cleaned_text = content_text
        if "```json" in cleaned_text:
            cleaned_text = cleaned_text.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned_text:
            cleaned_text = cleaned_text.split("```")[1].split("```")[0].strip()

        json_candidate = cleaned_text
        json_match = re.search(r"\{[\s\S]*\}", cleaned_text)
        if json_match:
            json_candidate = json_match.group(0)

        parsed = json.loads(json_candidate, strict=False)
        answer = parsed.get("answer", cleaned_text)
        refs = parsed.get("referenced_figures", figure_urls)
        cits = parsed.get("citations", list(set(citations)))
        contradictions = parsed.get("contradictions", [])
    except Exception as error:
        logger.warning("synthesizer_json_parse_fallback", error=str(error))
        answer = content_text if content_text else (
            f"Based on the archive evidence:\n\n"
            + "\n".join([f"- {c.content[:300]}..." for c in chunks[:3]])
        )
        refs = figure_urls
        cits = list(set(citations))
        contradictions = []

    return {
        "final_answer": answer,
        "referenced_figures": refs,
        "citations": cits,
        "contradictions": contradictions,
    }
