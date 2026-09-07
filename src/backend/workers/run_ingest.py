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
) -> int:
    metadata, figures, tables, text_content = parser.parse_document(file_path)
    chunks = chunker.chunk_document(metadata, text_content, figures, tables)

    if not chunks:
        logger.info("no_chunks_generated", file=str(file_path))
        return 0

    texts_to_embed = [chunk.content for chunk in chunks]
    embeddings = await embedder.embed_texts(texts_to_embed, input_type="document")

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
    logger.info("document_ingested", doc_id=metadata.doc_id, chunks_count=len(chunks))
    return len(chunks)


async def run_ingestion_pipeline(archive_dir: Path, force: bool = False) -> None:
    settings = get_settings()
    target_dir = archive_dir or settings.raw_archive_dir

    if not target_dir.exists():
        logger.error("archive_directory_not_found", path=str(target_dir))
        return

    logger.info("starting_ingestion_worker", target_directory=str(target_dir))
    await init_database()

    parser = DocumentParser()
    chunker = DocumentChunker()
    embedder = MultimodalEmbedder()

    supported_extensions = {".pdf", ".docx", ".md", ".txt", ".png", ".jpg", ".jpeg"}
    files_to_process = [
        p for p in target_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in supported_extensions and not p.name.startswith(".")
    ]

    logger.info("files_discovered", count=len(files_to_process))
    total_chunks = 0

    async with session_scope() as session:
        store = PostgresVectorStore(session)
        for index, file_path in enumerate(files_to_process, 1):
            logger.info("processing_file", index=index, total=len(files_to_process), file=file_path.name)
            try:
                count = await process_document(file_path, parser, chunker, embedder, store)
                total_chunks += count
            except Exception as error:
                logger.error("file_processing_error", file=str(file_path), error_detail=str(error))

    logger.info("ingestion_worker_completed", total_chunks=total_chunks)


def main() -> None:
    arg_parser = argparse.ArgumentParser(description="Offline Ingestion Worker for The Archivist")
    arg_parser.add_argument("--archive-dir", type=Path, default=None, help="Path to raw archive directory")
    arg_parser.add_argument("--force", action="store_true", help="Reprocess files even if already ingested")
    args = arg_parser.parse_args()

    asyncio.run(run_ingestion_pipeline(archive_dir=args.archive_dir, force=args.force))


if __name__ == "__main__":
    main()
