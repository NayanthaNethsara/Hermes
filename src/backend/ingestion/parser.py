import hashlib
from pathlib import Path
from typing import Any

from PIL import Image

from src.backend.core.config import get_settings
from src.backend.core.exceptions import DocumentParsingError
from src.backend.core.logging import get_logger
from src.backend.ingestion.schemas import (
    DocumentMetadata,
    EpistemicWeight,
    ExtractedFigure,
    ExtractedTable,
    SourceCategory,
)

logger = get_logger(__name__)


def compute_file_hash(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as stream:
        while chunk := stream.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def infer_source_category(file_path: Path) -> tuple[SourceCategory, float]:
    path_string = str(file_path).lower()
    if "codex" in path_string:
        return SourceCategory.CODEX, EpistemicWeight.CODEX.value
    if "wiki" in path_string:
        return SourceCategory.WIKI, EpistemicWeight.WIKI.value
    if "novel" in path_string or "book" in path_string:
        return SourceCategory.NOVEL, EpistemicWeight.NOVEL.value
    if "ephemera" in path_string or "letter" in path_string or "ledger" in path_string:
        return SourceCategory.EPHEMERA, EpistemicWeight.EPHEMERA.value
    if file_path.suffix.lower() in [".png", ".jpg", ".jpeg"]:
        return SourceCategory.IMAGE, EpistemicWeight.CODEX.value
    return SourceCategory.UNKNOWN, EpistemicWeight.UNKNOWN.value


class DocumentParser:
    def __init__(self, output_assets_dir: Path | None = None) -> None:
        settings = get_settings()
        self.output_assets_dir = output_assets_dir or settings.extracted_assets_dir
        self.output_assets_dir.mkdir(parents=True, exist_ok=True)

    def parse_document(
        self, file_path: Path
    ) -> tuple[DocumentMetadata, list[ExtractedFigure], list[ExtractedTable], str]:
        if not file_path.exists():
            raise DocumentParsingError(f"File not found: {file_path}")

        file_hash = compute_file_hash(file_path)
        category, weight = infer_source_category(file_path)
        metadata = DocumentMetadata(
            doc_id=file_path.stem,
            file_hash=file_hash,
            file_path=file_path,
            source_category=category,
            epistemic_weight=weight,
        )

        try:
            return self._parse_with_docling(file_path, metadata)
        except Exception as error:
            logger.warning(
                "docling_parser_fallback_triggered",
                file_path=str(file_path),
                error_detail=str(error),
            )
            return self._parse_with_fallback(file_path, metadata)

    def _parse_with_docling(
        self, file_path: Path, metadata: DocumentMetadata
    ) -> tuple[DocumentMetadata, list[ExtractedFigure], list[ExtractedTable], str]:
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(file_path)
        doc = result.document

        extracted_figures: list[ExtractedFigure] = []
        extracted_tables: list[ExtractedTable] = []

        raw_markdown = doc.export_to_markdown()
        return metadata, extracted_figures, extracted_tables, raw_markdown

    def _parse_with_fallback(
        self, file_path: Path, metadata: DocumentMetadata
    ) -> tuple[DocumentMetadata, list[ExtractedFigure], list[ExtractedTable], str]:
        suffix = file_path.suffix.lower()
        extracted_figures: list[ExtractedFigure] = []
        extracted_tables: list[ExtractedTable] = []

        if suffix in [".png", ".jpg", ".jpeg"]:
            figure_path = self.output_assets_dir / f"{metadata.file_hash[:12]}_full.png"
            image = Image.open(file_path)
            image.save(figure_path)
            extracted_figures.append(
                ExtractedFigure(
                    figure_id=f"{metadata.doc_id}_fig_0",
                    page_number=1,
                    bounding_box=(0.0, 0.0, float(image.width), float(image.height)),
                    local_image_path=figure_path,
                    caption=metadata.doc_id,
                )
            )
            return metadata, extracted_figures, extracted_tables, f"Visual Asset: {metadata.doc_id}"

        if suffix == ".pdf":
            import fitz

            document = fitz.open(file_path)
            metadata.page_count = len(document)
            full_text_parts: list[str] = []

            for page_index, page in enumerate(document):
                full_text_parts.append(page.get_text())
                image_list = page.get_images(full=True)
                for image_index, img_info in enumerate(image_list):
                    xref = img_info[0]
                    base_image = document.extract_image(xref)
                    image_bytes = base_image["image"]
                    ext = base_image["ext"]
                    image_filename = f"{metadata.file_hash[:12]}_p{page_index + 1}_img{image_index}.{ext}"
                    image_save_path = self.output_assets_dir / image_filename
                    with open(image_save_path, "wb") as image_file:
                        image_file.write(image_bytes)

                    extracted_figures.append(
                        ExtractedFigure(
                            figure_id=f"{metadata.doc_id}_p{page_index + 1}_img{image_index}",
                            page_number=page_index + 1,
                            bounding_box=(0.0, 0.0, 0.0, 0.0),
                            local_image_path=image_save_path,
                            caption=f"Extracted figure from page {page_index + 1}",
                        )
                    )

            return metadata, extracted_figures, extracted_tables, "\n\n".join(full_text_parts)

        text_content = file_path.read_text(encoding="utf-8", errors="ignore")
        return metadata, extracted_figures, extracted_tables, text_content
