import hashlib
import re
import shutil
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
from src.backend.ingestion.vision import VisionAnalyzer

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
    if "chronicles" in path_string or "novel" in path_string or "book" in path_string:
        return SourceCategory.NOVEL, EpistemicWeight.NOVEL.value
    if "ephemera" in path_string or "letter" in path_string or "ledger" in path_string:
        return SourceCategory.EPHEMERA, EpistemicWeight.EPHEMERA.value
    if file_path.suffix.lower() in [".png", ".jpg", ".jpeg"]:
        return SourceCategory.IMAGE, EpistemicWeight.CODEX.value
    return SourceCategory.UNKNOWN, EpistemicWeight.UNKNOWN.value


def generate_image_description(filename: str) -> str:
    name = Path(filename).stem
    clean_name = re.sub(r"^(atmo_|plate_\d+_)", "", name).replace("_", " ").title()
    name_lower = name.lower()
    if "heraldry" in name_lower or "banner" in name_lower:
        return f"Official heraldic banner, central emblem, and faction insignia of {clean_name}."
    if "portrait" in name_lower or "character" in name_lower:
        return f"Official illustration and character portrait of {clean_name}."
    if "creature" in name_lower or "threat" in name_lower:
        return f"Official threat-classification figure plate and anatomical diagram for creature {clean_name}."
    if "artifact" in name_lower or "relic" in name_lower:
        return f"Official figure plate, technical diagram, and attunement cost plate for relic {clean_name}."
    if "location" in name_lower or "landscape" in name_lower or "keep" in name_lower or "citadel" in name_lower:
        return f"Official figure plate, architectural view, and recorded garrison strength for {clean_name}."
    return f"Official figure plate and visual plate for {clean_name}."


def build_plate_registry(archive_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    plate_hashes: dict[str, str] = {}
    plate_titles: dict[str, str] = {}
    if not archive_dir.exists():
        return plate_hashes, plate_titles

    for plate_path in archive_dir.glob("**/plate_*.png"):
        try:
            with open(plate_path, "rb") as stream:
                digest = hashlib.sha256(stream.read()).hexdigest()[:12]
                plate_hashes[digest] = plate_path.name

            clean_title = re.sub(r"^plate_\d+_[a-z]+_", "", plate_path.stem.lower()).replace("_", " ")
            plate_titles[clean_title] = plate_path.name
            if clean_title.startswith("the "):
                plate_titles[clean_title.replace("the ", "", 1)] = plate_path.name
        except Exception:
            continue

    return plate_hashes, plate_titles


class DocumentParser:
    def __init__(self, output_assets_dir: Path | None = None) -> None:
        settings = get_settings()
        self.archive_dir = settings.raw_archive_dir
        self.output_assets_dir = output_assets_dir or settings.extracted_assets_dir
        self.output_assets_dir.mkdir(parents=True, exist_ok=True)
        self.vision_analyzer = VisionAnalyzer()
        self.catalog_path = self.output_assets_dir / "visual_catalog.json"
        self._visual_catalog: dict[str, Any] | None = None
        self.plate_hashes, self.plate_titles = build_plate_registry(self.archive_dir)

    @property
    def visual_catalog(self) -> dict[str, Any]:
        if self._visual_catalog is None:
            if self.catalog_path.exists():
                try:
                    import json
                    with open(self.catalog_path, "r", encoding="utf-8") as f:
                        self._visual_catalog = json.load(f)
                except Exception:
                    self._visual_catalog = {}
            else:
                self._visual_catalog = {}
        return self._visual_catalog

    def _build_visual_evidence_block(self, asset_filename: str) -> str:
        if asset_filename not in self.visual_catalog:
            return ""
        vis_data = self.visual_catalog[asset_filename]
        desc = vis_data.get("visual_description", "")
        txt = vis_data.get("extracted_text", "")
        elements = []
        if desc:
            elements.append(f"Visual Details: {desc}")
        if txt:
            elements.append(f"Inscribed Text: {txt}")
        if elements:
            return "\n> **[Visual Evidence]**: " + " | ".join(elements) + "\n"
        return ""

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

        suffix = file_path.suffix.lower()

        if suffix in [".png", ".jpg", ".jpeg"]:
            return self._parse_standalone_image(file_path, metadata)

        if suffix == ".md":
            return self._parse_markdown(file_path, metadata)

        if suffix == ".docx":
            return self._parse_docx(file_path, metadata)

        if suffix == ".pdf":
            return self._parse_pdf(file_path, metadata)

        if suffix == ".txt":
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            return metadata, [], [], content

        try:
            return self._parse_with_docling(file_path, metadata)
        except Exception as error:
            logger.warning("fallback_to_text", file=str(file_path), error_detail=str(error))
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            return metadata, [], [], content

    def _parse_standalone_image(
        self, file_path: Path, metadata: DocumentMetadata
    ) -> tuple[DocumentMetadata, list[ExtractedFigure], list[ExtractedTable], str]:
        asset_filename = f"{file_path.name}"
        destination_path = self.output_assets_dir / asset_filename
        if not destination_path.exists():
            shutil.copy2(file_path, destination_path)

        with Image.open(file_path) as img:
            width, height = img.size

        if asset_filename in self.visual_catalog:
            catalog_entry = self.visual_catalog[asset_filename]
            title = catalog_entry.get("title", metadata.doc_id)
            extracted_text = catalog_entry.get("extracted_text", "")
            caption = f"{title}: {extracted_text[:120]}" if extracted_text else title
            full_content = catalog_entry.get("rich_content")
            if not full_content:
                desc = catalog_entry.get("visual_description", "")
                attrs = catalog_entry.get("attributes", {})
                attrs_md = "\n".join([f"- **{k.replace('_', ' ').title()}**: {v}" for k, v in attrs.items()])
                full_content = (
                    f"# Visual Asset: {title}\n\n"
                    f"**File**: {asset_filename}\n"
                    f"**Asset Path**: /assets/{asset_filename}\n\n"
                    f"### Extracted Text & Data\n"
                    f"{extracted_text if extracted_text else 'No inscribed text detected.'}\n\n"
                    f"### Visual Scene Analysis\n"
                    f"{desc}\n\n"
                    f"### Key Attributes\n"
                    f"{attrs_md if attrs_md else 'None recorded.'}"
                )
        else:
            try:
                analysis = self.vision_analyzer.analyze_image(file_path)
                caption = f"{analysis.title}: {analysis.extracted_text[:120]}" if analysis.extracted_text else analysis.title
                full_content = analysis.rich_content
            except Exception as error:
                logger.warning("vision_analyzer_fallback", file=file_path.name, error_detail=str(error))
                description = generate_image_description(file_path.name)
                caption = description
                full_content = (
                    f"# Visual Figure Plate: {metadata.doc_id}\n\n"
                    f"{description}\n\n"
                    f"Asset Path: /assets/{asset_filename}\n"
                    f"Source: {file_path.name}"
                )

        figure = ExtractedFigure(
            figure_id=metadata.doc_id,
            page_number=1,
            bounding_box=(0.0, 0.0, float(width), float(height)),
            local_image_path=destination_path,
            caption=caption,
        )

        return metadata, [figure], [], full_content

    def _parse_markdown(
        self, file_path: Path, metadata: DocumentMetadata
    ) -> tuple[DocumentMetadata, list[ExtractedFigure], list[ExtractedTable], str]:
        text_content = file_path.read_text(encoding="utf-8", errors="ignore")
        extracted_figures: list[ExtractedFigure] = []

        image_pattern = re.compile(r"!\[(.*?)\]\((.*?)\)")
        matches = image_pattern.findall(text_content)

        for alt_text, image_rel_path in matches:
            resolved_image_path = (file_path.parent / image_rel_path).resolve()
            if resolved_image_path.exists():
                asset_filename = resolved_image_path.name
                destination_path = self.output_assets_dir / asset_filename
                if not destination_path.exists():
                    shutil.copy2(resolved_image_path, destination_path)

                visual_evidence = self._build_visual_evidence_block(asset_filename)
                old_tag = f"![{alt_text}]({image_rel_path})"
                new_tag = f"![{alt_text}](/assets/{asset_filename}){visual_evidence}"
                if old_tag in text_content:
                    text_content = text_content.replace(old_tag, new_tag)
                else:
                    text_content = text_content.replace(f"({image_rel_path})", f"(/assets/{asset_filename})")

                extracted_figures.append(
                    ExtractedFigure(
                        figure_id=f"{metadata.doc_id}_{resolved_image_path.stem}",
                        page_number=1,
                        bounding_box=(0.0, 0.0, 0.0, 0.0),
                        local_image_path=destination_path,
                        caption=alt_text or generate_image_description(resolved_image_path.name),
                    )
                )

        return metadata, extracted_figures, [], text_content

    def _parse_docx(
        self, file_path: Path, metadata: DocumentMetadata
    ) -> tuple[DocumentMetadata, list[ExtractedFigure], list[ExtractedTable], str]:
        import docx

        document = docx.Document(file_path)
        blocks: list[str] = []
        extracted_figures: list[ExtractedFigure] = []
        extracted_tables: list[ExtractedTable] = []

        for child in document.element.body:
            if child.tag.endswith("p"):
                paragraph = docx.text.paragraph.Paragraph(child, document)
                style_name = paragraph.style.name if paragraph.style else "Normal"
                text = paragraph.text.strip()
                paragraph_lines: list[str] = []

                if style_name == "Title" and text:
                    paragraph_lines.append(f"# {text}")
                elif style_name.startswith("Heading") and text:
                    level_match = re.search(r"\d+", style_name)
                    level = int(level_match.group(0)) if level_match else 2
                    paragraph_lines.append(f"{'#' * min(level, 4)} {text}")
                elif text:
                    paragraph_lines.append(text)

                blip_ids = paragraph._p.xpath(".//a:blip/@r:embed")
                for blip_id in blip_ids:
                    if blip_id in document.part.related_parts:
                        image_part = document.part.related_parts[blip_id]
                        blob = image_part.blob
                        blob_hash = hashlib.sha256(blob).hexdigest()[:12]
                        plate_filename = self.plate_hashes.get(blob_hash)
                        if not plate_filename:
                            ext = image_part.content_type.split("/")[-1].replace("jpeg", "jpg")
                            plate_filename = f"{metadata.file_hash[:8]}_{file_path.stem}_{blob_hash}.{ext}"

                        destination_path = self.output_assets_dir / plate_filename
                        if not destination_path.exists():
                            with open(destination_path, "wb") as f:
                                f.write(blob)

                        visual_evidence = self._build_visual_evidence_block(plate_filename)
                        paragraph_lines.append(f"![Figure](/assets/{plate_filename}){visual_evidence}")
                        extracted_figures.append(
                            ExtractedFigure(
                                figure_id=f"{metadata.doc_id}_{plate_filename}",
                                page_number=1,
                                bounding_box=(0.0, 0.0, 0.0, 0.0),
                                local_image_path=destination_path,
                                caption=generate_image_description(plate_filename),
                            )
                        )

                if paragraph_lines:
                    blocks.append("\n\n".join(paragraph_lines))

            elif child.tag.endswith("tbl"):
                table = docx.table.Table(child, document)
                rows_data: list[list[str]] = []
                for row in table.rows:
                    rows_data.append([cell.text.strip().replace("\n", " ") for cell in row.cells])
                if rows_data:
                    header = "| " + " | ".join(rows_data[0]) + " |"
                    separator = "| " + " | ".join(["---"] * len(rows_data[0])) + " |"
                    body = "\n".join("| " + " | ".join(row) + " |" for row in rows_data[1:])
                    table_markdown = f"{header}\n{separator}\n{body}"
                    blocks.append(table_markdown)
                    extracted_tables.append(
                        ExtractedTable(
                            table_id=f"{metadata.doc_id}_tbl_{len(extracted_tables)}",
                            page_number=1,
                            bounding_box=(0.0, 0.0, 0.0, 0.0),
                            markdown_content=table_markdown,
                        )
                    )

        full_content = "\n\n".join(blocks)
        return metadata, extracted_figures, extracted_tables, full_content

    def _parse_pdf(
        self, file_path: Path, metadata: DocumentMetadata
    ) -> tuple[DocumentMetadata, list[ExtractedFigure], list[ExtractedTable], str]:
        import fitz

        document = fitz.open(file_path)
        metadata.page_count = len(document)
        text_parts: list[str] = []
        extracted_figures: list[ExtractedFigure] = []

        is_scanned_pdf = ".scan" in file_path.name.lower()

        for page_index, page in enumerate(document):
            page_text = page.get_text().strip()
            page_figure_markers: list[str] = []

            matched_canonical_plate: str | None = None
            for title_key, plate_file in self.plate_titles.items():
                if title_key in page_text.lower():
                    matched_canonical_plate = plate_file
                    break

            image_list = page.get_images(full=True)
            for image_index, img_info in enumerate(image_list):
                xref = img_info[0]
                base_image = document.extract_image(xref)
                image_bytes = base_image["image"]
                ext = base_image["ext"]

                blob_hash = hashlib.sha256(image_bytes).hexdigest()[:12]
                plate_filename = self.plate_hashes.get(blob_hash) or matched_canonical_plate
                if not plate_filename:
                    plate_filename = f"{metadata.file_hash[:8]}_{file_path.stem}_p{page_index + 1}_{image_index}.{ext}"

                dest = self.output_assets_dir / plate_filename
                if not dest.exists():
                    with open(dest, "wb") as f:
                        f.write(image_bytes)

                visual_evidence = self._build_visual_evidence_block(plate_filename)
                page_figure_markers.append(f"![Figure p.{page_index + 1}](/assets/{plate_filename}){visual_evidence}")
                extracted_figures.append(
                    ExtractedFigure(
                        figure_id=f"{metadata.doc_id}_p{page_index + 1}_{plate_filename}",
                        page_number=page_index + 1,
                        bounding_box=(0.0, 0.0, 0.0, 0.0),
                        local_image_path=dest,
                        caption=generate_image_description(plate_filename),
                    )
                )

            figures_str = "\n".join(page_figure_markers)

            if is_scanned_pdf and not page_text:
                page_pix = page.get_pixmap(dpi=150)
                scan_filename = f"scan_{metadata.file_hash[:8]}_{file_path.stem}_p{page_index + 1}.png"
                scan_dest = self.output_assets_dir / scan_filename
                if not scan_dest.exists():
                    page_pix.save(str(scan_dest))

                if scan_filename in self.visual_catalog:
                    cached_content = self.visual_catalog[scan_filename].get("rich_content", "")
                    text_parts.append(
                        f"## Page {page_index + 1} (Historical Scan Analysis)\n\n"
                        f"![Historical Document Scan](/assets/{scan_filename})\n\n"
                        f"{cached_content}"
                    )
                else:
                    try:
                        analysis = self.vision_analyzer.analyze_image(scan_dest)
                        text_parts.append(
                            f"## Page {page_index + 1} (Historical Scan Analysis)\n\n"
                            f"![Historical Document Scan](/assets/{scan_filename})\n\n"
                            f"{analysis.rich_content}"
                        )
                    except Exception as vision_err:
                        logger.warning("scan_vision_analysis_failed", file=file_path.name, page=page_index + 1, error=str(vision_err))
                        text_parts.append(
                            f"## Page {page_index + 1}\n\n![Historical Document Scan](/assets/{scan_filename})"
                        )
            elif page_text:
                if figures_str:
                    text_parts.append(f"## Page {page_index + 1}\n\n{page_text}\n\n{figures_str}")
                else:
                    text_parts.append(f"## Page {page_index + 1}\n\n{page_text}")
            elif figures_str:
                text_parts.append(f"## Page {page_index + 1}\n\n{figures_str}")

        content = "\n\n".join(text_parts) if text_parts else f"Document {file_path.stem}"
        return metadata, extracted_figures, [], content

    def _parse_with_docling(
        self, file_path: Path, metadata: DocumentMetadata
    ) -> tuple[DocumentMetadata, list[ExtractedFigure], list[ExtractedTable], str]:
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(file_path)
        doc = result.document
        raw_markdown = doc.export_to_markdown()
        return metadata, [], [], raw_markdown
