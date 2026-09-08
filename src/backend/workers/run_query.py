import argparse
import asyncio
import sys

from src.backend.agents.graphs.investigator_1c import build_investigator_1c_graph
from src.backend.agents.graphs.multimodal_1a import build_multimodal_1a_graph
from src.backend.agents.state.base import create_initial_state


def format_separator(character: str = "=", length: int = 80) -> str:
    return character * length


async def execute_query(question: str, track: str = "1a") -> None:
    print(format_separator("="))
    print("THE ARCHIVIST — MULTIMODAL EVIDENCE & EMBEDDING INSPECTOR")
    print(f"Track: {track.upper()}")
    print(f"Question: {question}")
    print(format_separator("="))
    print()

    if track in ["1c", "investigator"]:
        graph = build_investigator_1c_graph()
    else:
        graph = build_multimodal_1a_graph()

    initial_state = create_initial_state(query=question)
    result = await graph.ainvoke(initial_state)

    retrieved_chunks = result.get("retrieved_context", [])
    print(format_separator("-"))
    print(f"RETRIEVED EVIDENCE CHUNKS ({len(retrieved_chunks)} MATCHES)")
    print(format_separator("-"))

    if not retrieved_chunks:
        print("No evidence chunks were retrieved.")
    else:
        for rank, chunk in enumerate(retrieved_chunks, 1):
            meta = chunk.metadata_payload or {}
            category = meta.get("source_category", "unknown")
            authority = meta.get("epistemic_weight", 0.5)
            section = meta.get("section_title", "General")
            vector_score = f"{chunk.vector_score:.4f}" if chunk.vector_score is not None else "N/A"
            keyword_score = f"{chunk.keyword_score:.4f}" if chunk.keyword_score is not None else "N/A"
            rrf_score = f"{chunk.relevance_score:.4f}"

            print(f"[{rank}] Document: {chunk.doc_id} (Section: {section})")
            print(f"    Category: {category.upper()} | Epistemic Authority: {authority}")
            print(f"    Cosine Similarity: {vector_score} | Full-Text Rank: {keyword_score} | Combined RRF: {rrf_score}")
            if chunk.figure_references:
                print(f"    Figures: {chunk.figure_references}")
            preview = chunk.content.strip().replace("\n", " ")
            if len(preview) > 300:
                preview = preview[:297] + "..."
            print(f"    Snippet: \"{preview}\"")
            print()

    figures = result.get("referenced_figures", [])
    print(format_separator("-"))
    print(f"REFERENCED FIGURES ({len(figures)})")
    print(format_separator("-"))
    if figures:
        for figure in figures:
            print(f"  - {figure}")
    else:
        print("  None")
    print()

    contradictions = result.get("contradictions", [])
    if contradictions:
        print(format_separator("-"))
        print(f"DETECTED CONTRADICTIONS ({len(contradictions)})")
        print(format_separator("-"))
        for item in contradictions:
            topic = item.get("topic", "Contradiction")
            sources = ", ".join(item.get("sources_disagree", []))
            print(f"  - [{topic}]: {sources}")
        print()

    answer = result.get("final_answer", "")
    print(format_separator("="))
    print("SYNTHESIZED ANSWER")
    print(format_separator("="))
    print(answer)
    print(format_separator("="))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run query against Archivist RAG pipeline with embedding visibility")
    parser.add_argument("--question", "-q", type=str, required=True, help="Question to ask")
    parser.add_argument("--track", "-t", type=str, default="1a", choices=["1a", "1c"], help="Graph track (1a or 1c)")
    args = parser.parse_args()

    asyncio.run(execute_query(question=args.question, track=args.track))


if __name__ == "__main__":
    main()
