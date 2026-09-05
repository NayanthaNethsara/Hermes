"""Ingest the Ashen Era Archive corpus into a local Chroma vector database.

What it does:
    Walks a corpus folder recursively, extracts text from every supported
    document (.pdf, .docx, .md, .txt, and scanned images via OCR), splits
    each document into ~300-500 word chunks, tags each chunk with a
    source_type and trust_tier, embeds the chunks with Voyage AI, and
    upserts everything into a persistent Chroma collection named
    "archive_chunks" stored at data/chroma/.

How to run it:
    1. Copy configuration-example/.env.example to .env at the repo root
       and fill in VOYAGE_API_KEY.
    2. From the repo root:
           python -m src.ingestion.ingest --corpus-path /path/to/corpus
       (or: python src/ingestion/ingest.py --corpus-path /path/to/corpus)

Safe to re-run: chunk_id is used as the Chroma document id, so re-running
this script on the same corpus overwrites existing chunks instead of
duplicating them.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import chromadb
import requests
from docx import Document as DocxDocument
from dotenv import load_dotenv
from pypdf import PdfReader
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
CHROMA_DIR = REPO_ROOT / "data" / "chroma"
COLLECTION_NAME = "archive_chunks"

# Overridable via .env so the model/endpoint can be swapped without a code
# change if the free tier or model availability shifts. NOTE: Voyage's
# contextualized-embedding models are served from a *different* endpoint
# (/v1/contextualizedembeddings) with a different payload shape than the
# standard /v1/embeddings used here - if embedding 400s on the configured
# model, set VOYAGE_MODEL to a standard model (e.g. voyage-3.5-lite).
VOYAGE_API_URL = os.environ.get(
    "VOYAGE_API_URL", "https://api.voyageai.com/v1/embeddings"
)
VOYAGE_MODEL = os.environ.get("VOYAGE_MODEL", "voyage-context-4")
EMBED_BATCH_SIZE = 32

MIN_CHUNK_WORDS = 300
MAX_CHUNK_WORDS = 500

DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

# source_type -> trust_tier, per docs/architecture.md section 5.
TRUST_TIERS = {
    "codex": "high",
    "wiki": "medium",
    "novel": "medium-low",
    "ephemera": "low",
}

# Keywords checked (in order) against a file's folder names and filename to
# infer its source_type. Update this once the real corpus folder names are
# known — see the "could not classify" warning printed at the end of a run.
SOURCE_TYPE_KEYWORDS = {
    "codex": ["codex"],
    "wiki": ["wiki"],
    "novel": ["novel"],
    "ephemera": ["ephemera", "letter", "ledger", "ballad", "transcript"],
}

# Unclassified files default to the least-trusted tier rather than silently
# assuming they're reliable (CLAUDE.md rule 5: never overstate trust).
FALLBACK_SOURCE_TYPE = "ephemera"


@dataclass
class Chunk:
    chunk_id: str
    text: str
    source_doc: str
    page: int | None
    source_type: str
    trust_tier: str


@dataclass
class IngestStats:
    documents_processed: int = 0
    chunks_created: int = 0
    failed_files: list[str] = field(default_factory=list)
    unclassified_files: list[str] = field(default_factory=list)
    per_source_type: dict[str, int] = field(default_factory=dict)


def slugify(text: str) -> str:
    """Turn arbitrary text into a lowercase, filesystem/id-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "doc"


def classify_source_type(path: Path, corpus_root: Path) -> str | None:
    """Infer a document's source_type from its folder names and filename.

    Checks the relative folder path first, then the filename itself,
    against SOURCE_TYPE_KEYWORDS. Returns None if nothing matches.
    """
    relative_parts = path.relative_to(corpus_root).parts[:-1]
    haystack = " ".join(relative_parts).lower() + " " + path.stem.lower()
    for source_type, keywords in SOURCE_TYPE_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return source_type
    return None


def split_into_paragraphs(text: str) -> list[str]:
    """Split text on blank lines, falling back to single newlines."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) > 1:
        return paragraphs
    return [p.strip() for p in text.splitlines() if p.strip()]


def chunk_text(text: str) -> list[str]:
    """Greedily group paragraphs into ~300-500 word chunks.

    Keeps paragraph boundaries intact where possible. A single paragraph
    longer than MAX_CHUNK_WORDS becomes its own (oversized) chunk rather
    than being cut mid-sentence.
    """
    chunks: list[str] = []
    buffer: list[str] = []
    buffer_words = 0

    for paragraph in split_into_paragraphs(text):
        paragraph_words = len(paragraph.split())

        if buffer and buffer_words + paragraph_words > MAX_CHUNK_WORDS:
            chunks.append("\n\n".join(buffer))
            buffer, buffer_words = [], 0

        buffer.append(paragraph)
        buffer_words += paragraph_words

        if buffer_words >= MIN_CHUNK_WORDS:
            chunks.append("\n\n".join(buffer))
            buffer, buffer_words = [], 0

    if buffer:
        chunks.append("\n\n".join(buffer))

    return chunks


def extract_pdf_pages(path: Path) -> list[tuple[int, str]]:
    """Return a list of (page_number, text) for every non-empty PDF page."""
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append((i, text))
    return pages


def extract_docx_text(path: Path) -> str:
    doc = DocxDocument(str(path))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_plain_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_image_text(path: Path) -> str:
    """OCR a scanned/image file with pytesseract."""
    import pytesseract
    from PIL import Image

    with Image.open(path) as image:
        return pytesseract.image_to_string(image)


def build_chunks_for_document(
    path: Path, corpus_root: Path, stats: IngestStats
) -> list[Chunk]:
    """Extract, classify, and chunk a single document. May raise on parse failure."""
    suffix = path.suffix.lower()
    doc_slug = slugify(str(path.relative_to(corpus_root).with_suffix("")))
    source_doc = path.name

    source_type = classify_source_type(path, corpus_root)
    if source_type is None:
        print(f"WARNING: could not classify source_type for {path} - "
              f"defaulting to '{FALLBACK_SOURCE_TYPE}'")
        stats.unclassified_files.append(str(path))
        source_type = FALLBACK_SOURCE_TYPE
    trust_tier = TRUST_TIERS[source_type]

    chunks: list[Chunk] = []

    if suffix == ".pdf":
        for page_num, page_text in extract_pdf_pages(path):
            for i, text in enumerate(chunk_text(page_text)):
                chunks.append(
                    Chunk(
                        chunk_id=f"{doc_slug}_p{page_num}_c{i}",
                        text=text,
                        source_doc=source_doc,
                        page=page_num,
                        source_type=source_type,
                        trust_tier=trust_tier,
                    )
                )
    else:
        if suffix == ".docx":
            text = extract_docx_text(path)
        elif suffix in (".md", ".txt"):
            text = extract_plain_text(path)
        elif suffix in IMAGE_EXTENSIONS:
            text = extract_image_text(path)
        else:
            raise ValueError(f"unsupported file type: {suffix}")

        for i, chunk in enumerate(chunk_text(text)):
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_slug}_c{i}",
                    text=chunk,
                    source_doc=source_doc,
                    page=None,
                    source_type=source_type,
                    trust_tier=trust_tier,
                )
            )

    return chunks


def require_voyage_api_key() -> str:
    """Fetch VOYAGE_API_KEY or fail fast with a clear message.

    Checked once up front (not inside embed_batch) so a missing key fails
    immediately instead of being retried five times by tenacity and
    surfacing as an opaque RetryError.
    """
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "VOYAGE_API_KEY is not set - copy configuration-example/.env.example "
            "to .env at the repo root and fill it in"
        )
    return api_key


@retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(5))
def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts with Voyage AI (voyage-context-4). Retries with
    exponential backoff (1s, 2s, 4s, 8s) since the free tier rate-limits."""
    response = requests.post(
        VOYAGE_API_URL,
        headers={"Authorization": f"Bearer {require_voyage_api_key()}"},
        json={"input": texts, "model": VOYAGE_MODEL},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()["data"]
    return [item["embedding"] for item in data]


def embed_chunks(chunks: list[Chunk]) -> list[list[float]]:
    """Embed a list of chunks in batches to stay within API payload limits."""
    embeddings: list[list[float]] = []
    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[start : start + EMBED_BATCH_SIZE]
        embeddings.extend(embed_batch([c.text for c in batch]))
    return embeddings


def iter_corpus_files(corpus_root: Path):
    supported = DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS
    for path in sorted(corpus_root.rglob("*")):
        if path.is_file() and path.suffix.lower() in supported:
            yield path


def upsert_chunks(collection, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
    """Upsert by chunk_id so re-running ingestion overwrites instead of duplicating."""
    collection.upsert(
        ids=[c.chunk_id for c in chunks],
        embeddings=embeddings,
        documents=[c.text for c in chunks],
        metadatas=[
            {
                "source_doc": c.source_doc,
                "page": c.page if c.page is not None else -1,
                "source_type": c.source_type,
                "trust_tier": c.trust_tier,
            }
            for c in chunks
        ],
    )


def print_summary(stats: IngestStats) -> None:
    print("\n--- Ingestion summary ---")
    print(f"Documents processed: {stats.documents_processed}")
    print(f"Chunks created:      {stats.chunks_created}")
    print("Chunks per source_type:")
    for source_type, count in sorted(stats.per_source_type.items()):
        print(f"  {source_type:10s} {count}")
    print(f"Files that could not be classified: {len(stats.unclassified_files)}")
    for path in stats.unclassified_files:
        print(f"  - {path}")
    print(f"Files that failed to parse: {len(stats.failed_files)}")
    for path in stats.failed_files:
        print(f"  - {path}")


def run_ingestion(corpus_path: Path) -> IngestStats:
    require_voyage_api_key()

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection(COLLECTION_NAME)

    stats = IngestStats()

    for path in iter_corpus_files(corpus_path):
        try:
            chunks = build_chunks_for_document(path, corpus_path, stats)
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
            print(f"WARNING: failed to parse {path}: {exc}")
            stats.failed_files.append(str(path))
            continue

        if not chunks:
            continue

        embeddings = embed_chunks(chunks)
        upsert_chunks(collection, chunks, embeddings)

        stats.documents_processed += 1
        stats.chunks_created += len(chunks)
        source_type = chunks[0].source_type
        stats.per_source_type[source_type] = (
            stats.per_source_type.get(source_type, 0) + len(chunks)
        )

    return stats


def main() -> None:
    # Corpus filenames can contain non-ASCII characters; on a Windows
    # console (cp1252) printing those raises UnicodeEncodeError and would
    # kill the whole run. Degrade to "?" instead of crashing.
    sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus-path",
        required=True,
        type=Path,
        help="Root folder of the Ashen Era Archive corpus (read-only).",
    )
    args = parser.parse_args()

    corpus_path: Path = args.corpus_path
    if not corpus_path.is_dir():
        raise SystemExit(f"--corpus-path is not a directory: {corpus_path}")

    try:
        stats = run_ingestion(corpus_path)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None

    print_summary(stats)


if __name__ == "__main__":
    main()
