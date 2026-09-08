import argparse
import asyncio
import sys

from langchain_core.messages import HumanMessage

from src.backend.agents.graphs.workflow import build_unified_graph


def format_separator(character: str = "=", length: int = 80) -> str:
    return character * length


async def execute_query(question: str) -> None:
    print(format_separator("="))
    print("HERMES — EVIDENCE & EMBEDDING INSPECTOR")
    print(f"Question: {question}")
    print(format_separator("="))
    print()

    graph = build_unified_graph()
    initial_state = {
        "root_query": question,
        "messages": [HumanMessage(content=question)],
    }
    result = await graph.ainvoke(initial_state)

    retrieved_chunks = result.get("verified_chunks", []) or result.get("active_chunks", [])
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
    parser = argparse.ArgumentParser(description="Run a query against the Hermes retrieval pipeline with embedding visibility")
    parser.add_argument("--question", "-q", type=str, required=True, help="Question to ask")
    args = parser.parse_args()

    asyncio.run(execute_query(question=args.question))


if __name__ == "__main__":
    main()
