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
import time
from dataclasses import dataclass, field
from pathlib import Path

import chromadb
import requests
from docx import Document as DocxDocument
from dotenv import load_dotenv
from pypdf import PdfReader
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
CHROMA_DIR = REPO_ROOT / "data" / "chroma"
COLLECTION_NAME = "archive_chunks"

# Overridable via .env so the model can be swapped without a code change.
# "voyage-context-4" (the model originally specified for this project) does
# not exist - Voyage's real contextualized-embedding model is
# "voyage-context-3", served from a *different* endpoint
# (/v1/contextualizedembeddings) with a nested-list payload shape, not the
# flat list this file sends to /v1/embeddings. Using a real standard model
# here instead of switching endpoints - see docs/decisions.md.
VOYAGE_API_URL = os.environ.get(
    "VOYAGE_API_URL", "https://api.voyageai.com/v1/embeddings"
)
VOYAGE_MODEL = os.environ.get("VOYAGE_MODEL", "voyage-4-lite")
# An account with no payment method attached is capped at 3 RPM / 10K TPM
# (confirmed by hitting that 429 directly - see docs/decisions.md). Adding a
# payment method removes that cap - the free 200M-token allowance still
# applies even with a card on file, per Voyage's own error message - and was
# confirmed empirically afterward: 30 requests in ~23s, zero 429s
# (~78 req/min). These defaults assume a payment method IS attached; if
# you're still on the unverified tier, override in .env:
#   VOYAGE_EMBED_BATCH_SIZE=10
#   VOYAGE_REQUEST_INTERVAL_SECONDS=22
EMBED_BATCH_SIZE = int(os.environ.get("VOYAGE_EMBED_BATCH_SIZE", "32"))
VOYAGE_REQUEST_INTERVAL_SECONDS = float(
    os.environ.get("VOYAGE_REQUEST_INTERVAL_SECONDS", "1.5")
)

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
    chunks_skipped_already_embedded: int = 0
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


OCR_TIMEOUT_SECONDS = int(os.environ.get("OCR_TIMEOUT_SECONDS", "60"))
# DPI to render a PDF page at before OCR-ing it. Higher is more accurate but
# slower; 200 is a reasonable middle ground for OCR (not print-quality).
PDF_OCR_RENDER_DPI = int(os.environ.get("PDF_OCR_RENDER_DPI", "200"))


def _ocr_image(image) -> str:
    """OCR a PIL image with pytesseract.

    `timeout` is required here: without it, a single oversized or corrupt
    image can hang the tesseract subprocess indefinitely, and with it the
    entire ingestion run - a hang tenacity's retry logic can't see or
    recover from, since it isn't the kind of exception that gets raised
    and retried. On timeout, pytesseract raises RuntimeError, which every
    caller here treats as a normal parse failure via the per-file
    try/except in run_ingestion.
    """
    import pytesseract

    return pytesseract.image_to_string(image, timeout=OCR_TIMEOUT_SECONDS)


def extract_pdf_pages(path: Path) -> list[tuple[int, str]]:
    """Return a list of (page_number, text) for every non-empty PDF page.

    Tries normal text extraction first (cheap, exact). A page with no
    extractable text is assumed to be a scanned/image page - architecture.md
    4.1 explicitly requires OCR support for "simulated scans" in the corpus
    - so it's rendered to an image and OCR'd instead of being silently
    dropped. This is why PyMuPDF is a dependency: pypdf can't rasterize a
    page, only read whatever text layer it already has.
    """
    import pymupdf
    from PIL import Image
    import io

    reader = PdfReader(str(path))
    pages: list[tuple[int, str]] = []
    ocr_needed: list[int] = []

    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append((i, text))
        else:
            ocr_needed.append(i)

    if ocr_needed:
        rendered = pymupdf.open(str(path))
        for page_num in ocr_needed:
            pix = rendered[page_num - 1].get_pixmap(dpi=PDF_OCR_RENDER_DPI)
            with Image.open(io.BytesIO(pix.tobytes("png"))) as image:
                ocr_text = _ocr_image(image).strip()
            if ocr_text:
                pages.append((page_num, ocr_text))
        rendered.close()
        pages.sort(key=lambda p: p[0])

    return pages


def extract_docx_text(path: Path) -> str:
    doc = DocxDocument(str(path))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_plain_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_image_text(path: Path) -> str:
    """OCR a scanned/image file with pytesseract."""
    from PIL import Image

    with Image.open(path) as image:
        return _ocr_image(image)


def build_slug_map(corpus_root: Path) -> dict[Path, str]:
    """Compute each file's doc_slug, disambiguating files that would
    otherwise collide.

    chunk_id is built from doc_slug, and the natural scheme (extension
    stripped from the relative path) collides whenever the same document
    is provided in more than one format - e.g. "petition.docx" and
    "petition.pdf" both slugify to "petition". Without disambiguation,
    whichever file processes first "wins" the chunk_ids, and the resume
    logic (which checks "does this chunk_id already exist?") then makes
    every later file with the same base slug look already-done and skips
    it entirely - silently dropping its real content with no error and no
    warning.

    Only files that actually collide get the extension folded into their
    slug; every other file keeps the plain scheme, so this doesn't change
    (and doesn't invalidate/orphan) chunk_ids for the common case of
    already-embedded data.
    """
    files = list(iter_corpus_files(corpus_root))
    base_slugs: dict[str, list[Path]] = {}
    for path in files:
        base = slugify(str(path.relative_to(corpus_root).with_suffix("")))
        base_slugs.setdefault(base, []).append(path)

    slug_map: dict[Path, str] = {}
    for base, paths in base_slugs.items():
        if len(paths) == 1:
            slug_map[paths[0]] = base
        else:
            for path in paths:
                slug_map[path] = slugify(str(path.relative_to(corpus_root)))
    return slug_map


def build_chunks_for_document(
    path: Path, corpus_root: Path, doc_slug: str, stats: IngestStats
) -> list[Chunk]:
    """Extract, classify, and chunk a single document. May raise on parse failure."""
    suffix = path.suffix.lower()
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


def _is_retryable_api_error(exc: BaseException) -> bool:
    """True for transient errors worth retrying (network hiccup, timeout,
    429 rate-limit, 5xx) - False for a 4xx client error (bad model name,
    malformed request, bad auth), which is deterministic and will fail
    identically on every retry. Without this, tenacity burns the full
    ~15s backoff on an error that could never have succeeded."""
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))


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


_last_voyage_request_at = 0.0


def _throttle_voyage() -> None:
    """Sleep just long enough to keep at least VOYAGE_REQUEST_INTERVAL_SECONDS
    between successive Voyage requests.

    Backoff-on-failure alone isn't enough for an account with a very low
    requests-per-minute ceiling: without this, ingestion fires the next
    batch's request the instant the previous one succeeds, immediately
    re-triggering the same 429 that backoff just cleared.
    """
    global _last_voyage_request_at
    elapsed = time.monotonic() - _last_voyage_request_at
    remaining = VOYAGE_REQUEST_INTERVAL_SECONDS - elapsed
    if remaining > 0:
        time.sleep(remaining)
    _last_voyage_request_at = time.monotonic()


@retry(
    retry=retry_if_exception(_is_retryable_api_error),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(6),
)
def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts with Voyage AI (VOYAGE_MODEL). Retries with
    exponential backoff (2s, 4s, 8s, 16s, 30s - ~60s total) on transient
    errors (network, timeout, 429, 5xx) since the free tier rate-limits -
    but not on a 4xx client error like an invalid model name or bad
    request, which will never succeed no matter how many times it's
    retried."""
    _throttle_voyage()
    response = requests.post(
        VOYAGE_API_URL,
        headers={"Authorization": f"Bearer {require_voyage_api_key()}"},
        json={"input": texts, "model": VOYAGE_MODEL},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()["data"]
    return [item["embedding"] for item in data]


def embed_and_upsert_chunks(collection, chunks: list[Chunk]) -> None:
    """Embed chunks in batches, upserting each batch immediately after it's
    embedded - not once at the end for the whole document.

    This matters a lot under a strict rate limit: a large document (a few
    hundred pages can mean a few hundred chunks, i.e. dozens of Voyage
    requests spaced ~20s apart - several minutes) previously wasn't saved
    to Chroma at all until every one of its batches succeeded. If the
    process was interrupted partway through, all of that document's
    already-embedded batches were silently discarded, and the resume logic
    above had nothing to skip - the whole document had to be re-embedded
    from scratch. Upserting per-batch means each Voyage call's result is
    durable the moment it succeeds, and progress is visible incrementally
    instead of appearing frozen until a large document finishes.
    """
    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[start : start + EMBED_BATCH_SIZE]
        embeddings = embed_batch([c.text for c in batch])
        upsert_chunks(collection, batch, embeddings)


def iter_corpus_files(corpus_root: Path):
    supported = DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS
    for path in sorted(corpus_root.rglob("*")):
        if path.is_file() and path.suffix.lower() in supported:
            yield path


def _existing_chunk_ids(collection, chunk_ids: list[str]) -> set[str]:
    """Which of these chunk_ids are already in the collection.

    A local Chroma lookup, not a Voyage call - free to check even under a
    tight rate limit.
    """
    if not chunk_ids:
        return set()
    return set(collection.get(ids=chunk_ids, include=[])["ids"])


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
    if stats.chunks_skipped_already_embedded:
        print(
            f"Chunks skipped (already embedded by a previous run): "
            f"{stats.chunks_skipped_already_embedded}"
        )
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
    slug_map = build_slug_map(corpus_path)

    for path in iter_corpus_files(corpus_path):
        try:
            chunks = build_chunks_for_document(path, corpus_path, slug_map[path], stats)
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
            print(f"WARNING: failed to parse {path}: {exc}")
            stats.failed_files.append(str(path))
            continue

        if not chunks:
            continue

        # Resume support: skip chunks a previous (possibly interrupted) run
        # already embedded. chunk_id is deterministic from the file path and
        # chunk index, so this is a cheap local Chroma lookup, not a Voyage
        # call - it doesn't touch the rate-limited request budget. Without
        # this, re-running after an interruption re-embeds everything from
        # scratch, which on a strict free tier can cost most of an hour
        # just to get back to where the previous run already was.
        already_done = _existing_chunk_ids(collection, [c.chunk_id for c in chunks])
        new_chunks = [c for c in chunks if c.chunk_id not in already_done]

        if new_chunks:
            embed_and_upsert_chunks(collection, new_chunks)
        if already_done:
            stats.chunks_skipped_already_embedded += len(already_done)

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
