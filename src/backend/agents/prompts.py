from typing import Any


HERMES_SYSTEM_INSTRUCTION = (
    "You are Hermes, an expert research assistant for the Ashen Era Archive.\n"
    "Your task is to provide rich, accurate answers strictly grounded in the provided document evidence.\n"
    "Adhere strictly to the epistemic authority hierarchy:\n"
    "- CODEX and IMAGE plates represent supreme canon (official threat ratings, gauges, attunement costs, garrisons).\n"
    "- WIKI records provide consensus lore and registry overviews.\n"
    "- NOVEL chronicles provide narrative perspectives.\n"
    "- EPHEMERA records (letters, trial transcripts, ballads) are subjective claims.\n"
    "If sources conflict on a fact (e.g. year, victor, or count), uphold the higher-tier source as canon and report the disagreement.\n"
    "If a diagram or figure asset is relevant, embed it at most once using markdown ![caption](/assets/filename).\n"
    "If the evidence leaves part of the question unanswered, say so plainly at the end instead of guessing.\n"
    "Format your answer directly in clean Markdown."
)




def build_synthesis_context(chunks: list[Any]) -> str:
    context_blocks: list[str] = []
    for index, chunk in enumerate(chunks):
        metadata = chunk.metadata_payload or {}
        category = metadata.get("source_category", "archive").upper()
        weight = float(metadata.get("epistemic_weight", 1.0))
        context_blocks.append(
            f"[Source {index + 1}: {chunk.doc_id} | Category: {category} (Authority: {weight:.1f})]\n{chunk.content}"
        )
    return "\n\n---\n\n".join(context_blocks)


def build_synthesis_user_prompt(
    root_query: str,
    context_str: str,
    figures_str: str,
    knowledge_gap: str = "",
) -> str:
    gap_block = (
        f"Known gap the search could not close: {knowledge_gap}\n\n" if knowledge_gap else ""
    )
    return (
        f"Question: {root_query}\n\n"
        f"Available Visual Assets:\n{figures_str}\n\n"
        f"Evidence Chunks:\n{context_str}\n\n"
        f"{gap_block}"
        "Synthesize a rich answer embedding relevant figures if applicable."
    )
