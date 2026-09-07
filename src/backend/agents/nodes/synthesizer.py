import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.backend.agents.llm import get_chat_model
from src.backend.agents.state.models import AgentState


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
        context_blocks.append(
            f"[Source {index + 1}: {doc_id} (Score: {chunk.relevance_score:.2f})]\n{chunk.content}"
        )

    context_str = "\n\n---\n\n".join(context_blocks)
    figures_str = "\n".join(figure_urls) if figure_urls else "No extracted figures."

    system_instruction = (
        "You are the Archivist AI, an expert technical and historical assistant for the Ashen Era Archive.\n"
        "Your task is to provide rich, accurate answers strictly grounded in the provided document evidence.\n"
        "If a diagram, figure, or table asset is available, mention and embed it directly.\n"
        "Output ONLY a valid JSON object matching this schema:\n"
        '{"answer": "string", "referenced_figures": ["string"], "citations": ["string"]}'
    )

    user_prompt = (
        f"Question: {root_query}\n\n"
        f"Available Visual Assets:\n{figures_str}\n\n"
        f"Evidence Chunks:\n{context_str}\n\n"
        "Synthesize a rich answer embedding relevant figures if applicable."
    )

    llm = get_chat_model(temperature=0.1)
    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_instruction),
            HumanMessage(content=user_prompt),
        ])
        content_text = response.content.strip()

        if "```json" in content_text:
            content_text = content_text.split("```json")[1].split("```")[0].strip()
        elif "```" in content_text:
            content_text = content_text.split("```")[1].split("```")[0].strip()

        parsed = json.loads(content_text)
        answer = parsed.get("answer", content_text)
        refs = parsed.get("referenced_figures", figure_urls)
        cits = parsed.get("citations", list(set(citations)))
    except Exception:
        answer = (
            f"Based on the archive evidence:\n\n"
            + "\n".join([f"- {c.content[:300]}..." for c in chunks[:3]])
        )
        refs = figure_urls
        cits = list(set(citations))

    return {
        "final_answer": answer,
        "referenced_figures": refs,
        "citations": cits,
    }
