import argparse
import asyncio
from pathlib import Path

from src.backend.core.config import get_settings
from src.backend.core.database import init_database, session_scope
from src.backend.core.logging import configure_logging, get_logger
from src.backend.ingestion.chunker import DocumentChunker
from src.backend.ingestion.embedder import MultimodalEmbedder
from src.backend.ingestion.parser import DocumentParser, compute_file_hash
from src.backend.retrieval.vector_store import PostgresVectorStore

configure_logging()
logger = get_logger("ingestion_worker")


async def process_document(
    file_path: Path,
    parser: DocumentParser,
    chunker: DocumentChunker,
    embedder: MultimodalEmbedder,
    store: PostgresVectorStore,
    force: bool = False,
) -> int:
    file_hash = compute_file_hash(file_path)

    if not force:
        already_processed = await store.has_document(file_hash)
        if already_processed:
            logger.info("file_already_processed_skipping", file=file_path.name, hash=file_hash[:10])
            return 0
    else:
        await store.delete_document(file_hash)

    metadata, figures, tables, text_content = parser.parse_document(file_path)
    chunks = chunker.chunk_document(metadata, text_content, figures, tables)

    if not chunks:
        logger.info("no_chunks_generated", file=file_path.name)
        await store.record_document(
            doc_id=metadata.doc_id,
            file_hash=metadata.file_hash,
            file_path=str(file_path),
            source_category=metadata.source_category.value,
            epistemic_weight=metadata.epistemic_weight,
            chunk_count=0,
            figure_count=len(figures),
        )
        return 0

    texts_to_embed = [chunk.content for chunk in chunks]
    embeddings = await embedder.embed_texts(texts_to_embed, input_type="document")

    # Record parent document first to satisfy foreign key constraint
    await store.record_document(
        doc_id=metadata.doc_id,
        file_hash=metadata.file_hash,
        file_path=str(file_path),
        source_category=metadata.source_category.value,
        epistemic_weight=metadata.epistemic_weight,
        chunk_count=len(chunks),
        figure_count=len(figures),
    )

    insert_payloads: list[dict] = []
    for chunk, vector in zip(chunks, embeddings):
        payload = dict(chunk.metadata_payload)
        payload["figure_references"] = chunk.figure_references
        payload["table_references"] = chunk.table_references

        insert_payloads.append({
            "chunk_id": chunk.chunk_id,
            "doc_id": chunk.doc_id,
            "file_hash": chunk.file_hash,
            "content": chunk.content,
            "embedding": vector,
            "metadata_payload": payload,
        })

    await store.insert_chunks(insert_payloads)

    logger.info(
        "document_ingested",
        doc_id=metadata.doc_id,
        chunks=len(chunks),
        figures=len(figures),
        category=metadata.source_category.value,
    )
    return len(chunks)


def select_canonical_documents(file_paths: list[Path]) -> list[Path]:
    def format_preference(path: Path) -> int:
        suffix = path.suffix.lower()
        if suffix == ".md":
            return 0
        if suffix == ".docx":
            return 1
        if suffix == ".pdf":
            return 2
        if suffix == ".txt":
            return 3
        return 4

    grouped: dict[str, list[Path]] = {}
    for path in file_paths:
        if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            key = f"img_{path.name}"
        else:
            key = path.stem
        grouped.setdefault(key, []).append(path)

    canonical_files: list[Path] = []
    for files in grouped.values():
        files.sort(key=format_preference)
        canonical_files.append(files[0])

    return canonical_files


async def run_ingestion_pipeline(
    archive_dir: Path | None = None,
    folder_filter: str | None = None,
    limit: int | None = None,
    force: bool = False,
) -> None:
    settings = get_settings()
    target_dir = archive_dir or settings.raw_archive_dir

    if not target_dir.exists():
        logger.error("archive_directory_not_found", path=str(target_dir))
        return

    logger.info("starting_ingestion_pipeline", target_directory=str(target_dir), force=force)
    await init_database()

    parser = DocumentParser()
    chunker = DocumentChunker()
    embedder = MultimodalEmbedder()

    supported_extensions = {".pdf", ".docx", ".md", ".txt", ".png", ".jpg", ".jpeg"}
    all_files = [
        p for p in target_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in supported_extensions and not p.name.startswith(".")
    ]

    if folder_filter:
        folders = [f.strip().lower() for f in folder_filter.split(",")]
        all_files = [
            p for p in all_files if any(folder in p.parts for folder in folders)
        ]

    all_files = select_canonical_documents(all_files)

    def sort_priority(path: Path) -> int:
        parts = [p.lower() for p in path.parts]
        if "images" in parts:
            return 0
        if "wiki" in parts:
            return 1
        if "codex" in parts:
            return 2
        return 3

    all_files.sort(key=sort_priority)

    if limit and limit > 0:
        all_files = all_files[:limit]

    logger.info("files_queued_for_processing", total_files=len(all_files))
    total_chunks = 0

    for index, file_path in enumerate(all_files, 1):
        try:
            async with session_scope() as session:
                store = PostgresVectorStore(session)
                chunk_count = await process_document(
                    file_path=file_path,
                    parser=parser,
                    chunker=chunker,
                    embedder=embedder,
                    store=store,
                    force=force,
                )
                total_chunks += chunk_count
        except Exception as error:
            logger.error(
                "file_ingestion_failed",
                file=file_path.name,
                error_detail=str(error),
            )

    logger.info("ingestion_pipeline_complete", total_chunks=total_chunks)


def main() -> None:
    arg_parser = argparse.ArgumentParser(description="Offline ingestion worker for Hermes")
    arg_parser.add_argument("--archive-dir", type=Path, default=None, help="Path to raw archive directory")
    arg_parser.add_argument("--folder", type=str, default=None, help="Filter by folder names (comma-separated, e.g. 'images,wiki')")
    arg_parser.add_argument("--limit", type=int, default=None, help="Max number of files to process")
    arg_parser.add_argument("--force", action="store_true", help="Reprocess files even if already ingested")
    args = arg_parser.parse_args()

    asyncio.run(
        run_ingestion_pipeline(
            archive_dir=args.archive_dir,
            folder_filter=args.folder,
            limit=args.limit,
            force=args.force,
        )
    )


if __name__ == "__main__":
    main()
