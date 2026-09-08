import json
import re
from typing import Any, AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage

from src.backend.agents.llm import get_chat_model
from src.backend.agents.nodes.evaluator import evaluate_sufficiency
from src.backend.agents.nodes.planner import plan_search_queries
from src.backend.agents.nodes.retriever import retrieve_evidence
from src.backend.agents.nodes.visualizer import resolve_visual_assets
from src.backend.agents.state.base import create_initial_state
from src.backend.agents.state.models import AgentState
from src.backend.core.logging import get_logger
from src.backend.retrieval.schemas import SearchResultChunk

logger = get_logger("agent_stream")


def format_sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def build_sources_payload(chunks: list[SearchResultChunk]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for chunk in chunks:
        metadata = chunk.metadata_payload or {}
        category = metadata.get("source_category", "unknown")
        relevance = chunk.relevance_score or 0.0
        is_trusted = category in ["codex", "image"] or relevance > 0.7
        sources.append({
            "chunk_id": chunk.chunk_id,
            "title": chunk.doc_id,
            "section": metadata.get("section_title", "General"),
            "category": category,
            "epistemic_weight": metadata.get("epistemic_weight", 0.5),
            "vector_score": round(chunk.vector_score, 4) if chunk.vector_score is not None else None,
            "keyword_score": round(chunk.keyword_score, 4) if chunk.keyword_score is not None else None,
            "relevance_score": round(relevance, 4),
            "figures": chunk.figure_references,
            "trust": "high" if is_trusted else "medium",
            "snippet": chunk.content[:300],
        })
    return sources


async def stream_agent_track(
    track_id: str,
    query: str,
    max_iterations: int = 5,
) -> AsyncGenerator[str, None]:
    track_normalized = track_id.lower().replace("-", "_").replace("track_", "").strip()
    state = create_initial_state(query=query, max_iterations=max_iterations)

    try:
        if track_normalized in ["1c", "investigator", "investigator_1c"]:
            async for sse_block in _stream_track_1c(state):
                yield sse_block
        else:
            async for sse_block in _stream_track_1a(state):
                yield sse_block
    except Exception as stream_error:
        logger.error("agent_streaming_failed", error=str(stream_error))
        yield format_sse_event("error", {"error": str(stream_error)})


async def _stream_track_1a(state: AgentState) -> AsyncGenerator[str, None]:
    root_query = state.get("root_query", "")

    yield format_sse_event("status", {
        "stage": "retrieving",
        "message": "Searching archive with hybrid vector and keyword search...",
    })

    retriever_update = await retrieve_evidence(state)
    state.update(retriever_update)
    chunks = state.get("retrieved_context", [])

    yield format_sse_event("status", {
        "stage": "visualizing",
        "message": f"Linking visual evidence ({len(state.get('figures', []))} plates found)...",
    })

    visualizer_update = await resolve_visual_assets(state)
    state.update(visualizer_update)

    sources = build_sources_payload(chunks)
    referenced_figures = state.get("referenced_figures", [])
    citations = list(dict.fromkeys([chunk.doc_id for chunk in chunks]))
    reasoning_steps = [
        {"step": 1, "action": "Hybrid vector and keyword search", "found": f"{len(chunks)} chunks"},
        {"step": 2, "action": "Multimodal figure linking", "found": f"{len(referenced_figures)} figures"},
    ]

    yield format_sse_event("metadata", {
        "sources": sources,
        "referenced_figures": referenced_figures,
        "citations": citations,
        "reasoning_steps": reasoning_steps,
    })

    yield format_sse_event("status", {
        "stage": "synthesizing",
        "message": f"Synthesizing answer from {len(sources)} authoritative sources...",
    })

    async for sse_block in _stream_synthesis(
        root_query=root_query,
        chunks=chunks,
        figure_urls=state.get("figure_urls", []),
        referenced_figures=referenced_figures,
        citations=citations,
        sources=sources,
        reasoning_steps=reasoning_steps,
    ):
        yield sse_block


async def _stream_track_1c(state: AgentState) -> AsyncGenerator[str, None]:
    root_query = state.get("root_query", "")
    max_iterations = state.get("max_iterations", 5)

    iteration = 0
    while iteration < max_iterations:
        yield format_sse_event("status", {
            "stage": "planning",
            "message": f"Planning investigative queries (iteration {iteration + 1})...",
            "iteration": iteration + 1,
        })

        planner_update = await plan_search_queries(state)
        state.update(planner_update)

        queries_str = ", ".join(state.get("search_queries", []))
        yield format_sse_event("status", {
            "stage": "retrieving",
            "message": f"Searching archive for: {queries_str}",
            "iteration": iteration + 1,
        })

        retriever_update = await retrieve_evidence(state)
        state.update(retriever_update)

        yield format_sse_event("status", {
            "stage": "evaluating",
            "message": "Evaluating evidence sufficiency and contradictions...",
            "iteration": iteration + 1,
        })

        evaluator_update = await evaluate_sufficiency(state)
        state.update(evaluator_update)

        iteration += 1
        if state.get("is_sufficient", False):
            break

    yield format_sse_event("status", {
        "stage": "visualizing",
        "message": "Linking relevant visual plates and cross-references...",
    })

    visualizer_update = await resolve_visual_assets(state)
    state.update(visualizer_update)

    chunks = state.get("retrieved_context", [])
    sources = build_sources_payload(chunks)
    referenced_figures = state.get("referenced_figures", [])
    citations = list(dict.fromkeys([chunk.doc_id for chunk in chunks]))
    reasoning_steps = [
        {"step": 1, "action": f"Multi-hop iterative exploration ({iteration} iterations)", "found": f"{len(chunks)} chunks"},
        {"step": 2, "action": "Multimodal figure linking", "found": f"{len(referenced_figures)} figures"},
    ]

    yield format_sse_event("metadata", {
        "sources": sources,
        "referenced_figures": referenced_figures,
        "citations": citations,
        "reasoning_steps": reasoning_steps,
    })

    yield format_sse_event("status", {
        "stage": "synthesizing",
        "message": f"Synthesizing investigative verdict from {len(sources)} sources...",
    })

    async for sse_block in _stream_synthesis(
        root_query=root_query,
        chunks=chunks,
        figure_urls=state.get("figure_urls", []),
        referenced_figures=referenced_figures,
        citations=citations,
        sources=sources,
        reasoning_steps=reasoning_steps,
    ):
        yield sse_block


async def _stream_synthesis(
    root_query: str,
    chunks: list[SearchResultChunk],
    figure_urls: list[str],
    referenced_figures: list[str],
    citations: list[str],
    sources: list[dict[str, Any]],
    reasoning_steps: list[dict[str, Any]],
) -> AsyncGenerator[str, None]:
    context_blocks: list[str] = []
    for index, chunk in enumerate(chunks):
        metadata = chunk.metadata_payload or {}
        category = metadata.get("source_category", "archive").upper()
        weight = float(metadata.get("epistemic_weight", 1.0))
        context_blocks.append(
            f"[Source {index + 1}: {chunk.doc_id} | Category: {category} (Authority: {weight:.1f})]\n{chunk.content}"
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
        "If a diagram or figure asset is relevant, embed it at most once using markdown ![caption](/assets/filename).\n"
        "Format your answer directly in clean Markdown.\n"
        "If genuine contradictions exist between sources, explain them clearly in your response. "
        "At the very end of your response, if contradictions were identified, append this exact delimiter followed by a JSON array without duplicate items:\n"
        "__CONTRADICTIONS_JSON__\n"
        '[{"topic": "string", "sources_disagree": ["string"]}]'
    )

    user_prompt = (
        f"Question: {root_query}\n\n"
        f"Available Visual Assets:\n{figures_str}\n\n"
        f"Evidence Chunks:\n{context_str}\n\n"
        "Synthesize a rich answer embedding relevant figures if applicable."
    )

    llm = get_chat_model(temperature=0.1)

    accumulated_text = ""
    yielded_length = 0
    is_capturing_contradictions = False
    contradictions_buffer = ""
    sentinel = "__CONTRADICTIONS_JSON__"

    try:
        async for chunk in llm.astream([
            SystemMessage(content=system_instruction),
            HumanMessage(content=user_prompt),
        ]):
            raw_delta = chunk.content
            delta_str = (
                "".join(p if isinstance(p, str) else p.get("text", "") for p in raw_delta)
                if isinstance(raw_delta, list)
                else str(raw_delta)
            )

            if not delta_str:
                continue

            if is_capturing_contradictions:
                contradictions_buffer += delta_str
                continue

            accumulated_text += delta_str

            if sentinel in accumulated_text:
                is_capturing_contradictions = True
                split_parts = accumulated_text.split(sentinel, 1)
                visible_text = split_parts[0]
                contradictions_buffer = split_parts[1] if len(split_parts) > 1 else ""

                unyielded_visible = visible_text[yielded_length:]
                if unyielded_visible:
                    yield format_sse_event("token", {"delta": unyielded_visible})
                    yielded_length = len(visible_text)
                continue

            safe_length = len(accumulated_text)
            for k in range(1, len(sentinel)):
                if sentinel.startswith(accumulated_text[-k:]):
                    safe_length = len(accumulated_text) - k
                    break

            if safe_length > yielded_length:
                delta_to_yield = accumulated_text[yielded_length:safe_length]
                yield format_sse_event("token", {"delta": delta_to_yield})
                yielded_length = safe_length

    except Exception as error:
        logger.warning("streaming_llm_failed_falling_back", error=str(error))
        fallback_answer = (
            f"Based on the archive evidence:\n\n"
            + "\n".join([f"- {c.content[:300]}..." for c in chunks[:3]])
        )
        remaining = fallback_answer[yielded_length:] if len(fallback_answer) > yielded_length else fallback_answer
        if remaining:
            yield format_sse_event("token", {"delta": remaining})
        accumulated_text = fallback_answer

    final_answer = accumulated_text.split(sentinel)[0].strip()
    contradictions: list[dict[str, Any]] = []

    if contradictions_buffer:
        clean_json_str = contradictions_buffer.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(clean_json_str)
            if isinstance(parsed, list):
                contradictions = parsed
        except Exception:
            json_match = re.search(r"\[[\s\S]*\]", clean_json_str)
            if json_match:
                try:
                    contradictions = json.loads(json_match.group(0))
                except Exception:
                    contradictions = []

    unique_contradictions: list[dict[str, Any]] = []
    seen_topics: set[str] = set()
    for item in contradictions:
        if isinstance(item, dict):
            topic = str(item.get("topic", "")).strip().lower()
            if topic and topic not in seen_topics:
                seen_topics.add(topic)
                unique_contradictions.append(item)

    from pathlib import Path
    embedded_figures = [
        fig for fig in referenced_figures
        if Path(fig).name in final_answer or fig in final_answer
    ]
    actual_referenced_figures = embedded_figures if embedded_figures else referenced_figures[:1]

    yield format_sse_event("done", {
        "answer": final_answer,
        "referenced_figures": actual_referenced_figures,
        "citations": citations,
        "sources": sources,
        "reasoning_steps": reasoning_steps,
        "contradictions": unique_contradictions,
    })
