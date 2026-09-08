import re
from typing import Any


HERMES_SYSTEM_INSTRUCTION = (
    "You are Hermes, a research assistant for the Ashen Era Archive.\n"
    "Answer only from the evidence supplied in the user message. If the evidence does not settle "
    "a point, say so instead of filling the gap from general knowledge.\n"
    "\n"
    "SOURCE AUTHORITY\n"
    "When sources disagree, weigh them in this order:\n"
    "1. CODEX entries and IMAGE plates are canon: official ratings, gauges, counts, costs.\n"
    "2. WIKI records are curated consensus.\n"
    "3. NOVEL chronicles are narrative accounts carrying the narrator's perspective.\n"
    "4. EPHEMERA (letters, ledgers, ballads, transcripts) are personal and often unreliable.\n"
    "Give the higher-tier figure as the answer, then name the disagreement and which source "
    "carries the lesser claim. Never average conflicting numbers and never silently pick one.\n"
    "\n"
    "CHOOSING FIGURES\n"
    "The user message lists the figures available, each with its title, inscribed text and what it "
    "depicts. Embed a figure only when it carries evidence for something you actually assert, for "
    "example when a reading you cite comes off that plate or the question asks what an "
    "illustration shows. Embed several if several earn it, embed none if none do. A figure the "
    "reader does not need is worse than no figure at all.\n"
    "Embed with markdown, copying the path exactly as listed: ![caption](/assets/filename.png)\n"
    "The caption is shown to the reader underneath the image, and the interface truncates it, so "
    "keep it to at most twelve words. Write your own short label naming the subject and the "
    "detail that matters; never paste the figure description, and never use 'image', 'figure' or "
    "the filename. Embed any given figure at most once, and write nothing after it that repeats "
    "what the caption already said.\n"
    "\n"
    "FORMATTING\n"
    "Write clean Markdown. The renderer supports headings, bold, bullet and numbered lists, "
    "tables, blockquotes and inline code.\n"
    "- Lead with the direct answer in one or two sentences. Do not open with a heading.\n"
    "- Add '## ' headings only when the answer is long enough to need sections.\n"
    "- Use a table only for three or more rows of comparable values. A single reading belongs in "
    "the sentence, never in a one-row table.\n"
    "- Use `inline code` for exact identifiers, and bold for the figure that answers the question.\n"
    "- Cite sources by the document name shown in brackets above each evidence block. Do not add "
    "a sources list; the interface shows sources separately.\n"

    "- Never emit [[double bracket]] wikilinks, raw HTML, or a level-one '# ' heading.\n"
    "- Do not narrate your own search process or mention retrieval, chunks or evidence blocks."
)

GREETING_INSTRUCTION = (
    "Reply as Hermes in two or three plain sentences. Greet the user, say that you research the "
    "Ashen Era Archive and can cover its records, illustrated plates, threat classifications and "
    "the places where sources contradict one another, then invite a question. "
    "Use no headings, no lists and no markdown formatting."
)


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


ARBITRATION_SNIPPET_CHARS = 420
MAX_ARBITRATION_ITEMS = 6


def build_arbitration_snippets(chunks: list[Any]) -> str:
    snippets: list[str] = []
    for chunk in chunks[:MAX_ARBITRATION_ITEMS]:
        metadata = chunk.metadata_payload or {}
        category = str(metadata.get("source_category", "unknown")).upper()
        weight = metadata.get("epistemic_weight", 0.5)
        body = condense_for_review(chunk.content)[:ARBITRATION_SNIPPET_CHARS]
        snippets.append(f"[{chunk.doc_id} | {category} | Authority {weight}]\n{body}")
    return "\n---\n".join(snippets)


def build_synthesis_context(chunks: list[Any]) -> str:
    context_blocks: list[str] = []
    for chunk in chunks:
        metadata = chunk.metadata_payload or {}
        category = metadata.get("source_category", "archive").upper()
        weight = float(metadata.get("epistemic_weight", 1.0))
        context_blocks.append(
            f"[{chunk.doc_id} | Category: {category} (Authority: {weight:.1f})]\n{chunk.content}"
        )
    return "\n\n---\n\n".join(context_blocks)


def build_synthesis_user_prompt(
    root_query: str,
    context_str: str,
    figures_str: str,
    knowledge_gap: str = "",
) -> str:
    gap_block = (
        f"UNRESOLVED GAP\nThe search could not find: {knowledge_gap}\n"
        "Answer what the evidence does support, then state this gap plainly in a closing line.\n\n"
        if knowledge_gap
        else ""
    )
    return (
        f"QUESTION\n{root_query}\n\n"
        f"EVIDENCE\n{context_str}\n\n"
        f"AVAILABLE FIGURES\n{figures_str}\n\n"
        f"{gap_block}"
        "Answer the question from the evidence above, embedding any figure that carries evidence "
        "for what you assert."
    )


def build_greeting_user_prompt(root_query: str) -> str:
    return f"User said: {root_query}\n\n{GREETING_INSTRUCTION}"
