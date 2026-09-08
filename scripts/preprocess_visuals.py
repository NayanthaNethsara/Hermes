import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backend.core.config import get_settings
from src.backend.core.database import init_database, session_scope
from src.backend.core.logging import get_logger
from src.backend.ingestion.embedder import MultimodalEmbedder
from src.backend.ingestion.parser import compute_file_hash
from src.backend.ingestion.schemas import EpistemicWeight, SourceCategory
from src.backend.ingestion.vision import VisionAnalyzer
from src.backend.retrieval.vector_store import PostgresVectorStore

logger = get_logger("preprocess_visuals")


async def preprocess_visual_archive(limit: int | None = None) -> None:
    settings = get_settings()
    archive_dir = settings.raw_archive_dir
    assets_dir = settings.extracted_assets_dir
    assets_dir.mkdir(parents=True, exist_ok=True)

    await init_database()
    analyzer = VisionAnalyzer()
    embedder = MultimodalEmbedder()

    image_extensions = {".png", ".jpg", ".jpeg"}
    all_images = [
        p for p in archive_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in image_extensions and not p.name.startswith(".")
    ]

    # Deduplicate by filename
    unique_images: dict[str, Path] = {}
    for p in all_images:
        if p.name not in unique_images:
            unique_images[p.name] = p

    images_list = sorted(list(unique_images.values()), key=lambda x: x.name)
    if limit and limit > 0:
        images_list = images_list[:limit]

    logger.info("visual_images_discovered", count=len(images_list))

    catalog: dict[str, dict] = {}
    processed_count = 0

    for index, image_path in enumerate(images_list, 1):
        file_hash = compute_file_hash(image_path)
        doc_id = image_path.stem
        asset_filename = image_path.name
        asset_rel_path = f"/assets/{asset_filename}"

        # Copy to extracted assets if not present
        destination_path = assets_dir / asset_filename
        if not destination_path.exists():
            import shutil
            shutil.copy2(image_path, destination_path)

        async with session_scope() as session:
            store = PostgresVectorStore(session)
            already_processed = await store.has_document(file_hash)
            if already_processed:
                logger.info(
                    "image_already_indexed_skipping",
                    file=asset_filename,
                    progress=f"{index}/{len(images_list)}",
                )
                continue

        logger.info(
            "analyzing_visual_asset_with_vision_llm",
            file=asset_filename,
            progress=f"{index}/{len(images_list)}",
        )

        try:
            analysis = analyzer.analyze_image(image_path)
        except Exception as error:
            logger.error("vision_analysis_failed", file=asset_filename, error=str(error))
            continue

        catalog[asset_filename] = {
            "title": analysis.title,
            "extracted_text": analysis.extracted_text,
            "visual_description": analysis.visual_description,
            "attributes": analysis.attributes,
            "asset_path": asset_rel_path,
        }

        # Embed the rich textual visual intelligence
        embedding = (await embedder.embed_texts([analysis.rich_content]))[0]

        async with session_scope() as session:
            store = PostgresVectorStore(session)
            await store.record_document(
                doc_id=doc_id,
                file_hash=file_hash,
                file_path=str(image_path),
                source_category=SourceCategory.IMAGE.value,
                epistemic_weight=EpistemicWeight.CODEX.value,
                chunk_count=1,
                figure_count=1,
            )

            chunk_id = f"{file_hash[:10]}_{doc_id}_0"
            payload = {
                "source_category": SourceCategory.IMAGE.value,
                "epistemic_weight": EpistemicWeight.CODEX.value,
                "file_path": str(image_path),
                "section_title": analysis.title,
                "figure_references": [asset_rel_path],
                "table_references": [],
            }

            await store.insert_chunks([{
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "file_hash": file_hash,
                "content": analysis.rich_content,
                "embedding": embedding,
                "metadata_payload": payload,
            }])

        processed_count += 1
        logger.info(
            "visual_asset_indexed_successfully",
            file=asset_filename,
            title=analysis.title,
        )

    catalog_path = assets_dir / "visual_catalog.json"
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    logger.info("visual_preprocessing_completed", newly_indexed=processed_count, catalog_path=str(catalog_path))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Preprocess visual archive using Gemini Vision and Voyage AI")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of images to process")
    args = parser.parse_args()

    asyncio.run(preprocess_visual_archive(limit=args.limit))
