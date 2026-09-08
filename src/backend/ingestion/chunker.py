import re
from typing import Any

from src.backend.ingestion.schemas import (
    DocumentMetadata,
    ExtractedFigure,
    ExtractedTable,
    SourceCategory,
    TextChunk,
)


class DocumentChunker:
    def __init__(self, target_chunk_size: int = 800, chunk_overlap: int = 100) -> None:
        self.target_chunk_size = target_chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_document(
        self,
        metadata: DocumentMetadata,
        raw_text: str,
        figures: list[ExtractedFigure],
        tables: list[ExtractedTable],
    ) -> list[TextChunk]:
        sections = self._split_by_headings(raw_text)
        chunks: list[TextChunk] = []
        chunk_sequence = 0

        figure_references = [str(figure.local_image_path) for figure in figures]
        table_references = [
            str(table.local_image_path) for table in tables if table.local_image_path
        ]

        for section_title, section_body in sections:
            paragraphs = [p.strip() for p in section_body.split("\n\n") if p.strip()]
            current_buffer: list[str] = []
            current_length = 0

            for paragraph in paragraphs:
                paragraph_length = len(paragraph)
                if current_length + paragraph_length > self.target_chunk_size and current_buffer:
                    chunk_text = "\n\n".join(current_buffer)
                    chunks.append(
                        self._create_chunk(
                            metadata=metadata,
                            sequence_index=chunk_sequence,
                            content=chunk_text,
                            section_title=section_title,
                            all_figures=figures,
                            table_refs=table_references,
                        )
                    )
                    chunk_sequence += 1
                    current_buffer = [paragraph]
                    current_length = paragraph_length
                else:
                    current_buffer.append(paragraph)
                    current_length += paragraph_length

            if current_buffer:
                chunk_text = "\n\n".join(current_buffer)
                chunks.append(
                    self._create_chunk(
                        metadata=metadata,
                        sequence_index=chunk_sequence,
                        content=chunk_text,
                        section_title=section_title,
                        all_figures=figures,
                        table_refs=table_references,
                    )
                )
                chunk_sequence += 1

        if not chunks and raw_text.strip():
            chunks.append(
                self._create_chunk(
                    metadata=metadata,
                    sequence_index=0,
                    content=raw_text.strip(),
                    section_title=metadata.doc_id,
                    all_figures=figures,
                    table_refs=table_references,
                )
            )

        return chunks

    def _split_by_headings(self, text: str) -> list[tuple[str, str]]:
        heading_pattern = re.compile(r"^(#{1,4}\s+.+)$", re.MULTILINE)
        splits = heading_pattern.split(text)

        if len(splits) <= 1:
            return [("General", text)]

        sections: list[tuple[str, str]] = []
        current_title = "Introduction"
        current_body = splits[0]
        if current_body.strip():
            sections.append((current_title, current_body))

        for i in range(1, len(splits), 2):
            header = splits[i].lstrip("#").strip()
            body = splits[i + 1] if i + 1 < len(splits) else ""
            sections.append((header, body))

        return sections

    def _create_chunk(
        self,
        metadata: DocumentMetadata,
        sequence_index: int,
        content: str,
        section_title: str,
        all_figures: list[ExtractedFigure],
        table_refs: list[str],
    ) -> TextChunk:
        chunk_id = f"{metadata.file_hash[:10]}_{metadata.doc_id}_{sequence_index}"

        # Match figures that actually appear or are referenced in this chunk's content
        matched_figure_refs: list[str] = []
        for fig in all_figures:
            asset_filename = fig.local_image_path.name
            asset_rel_path = f"/assets/{asset_filename}"
            if asset_rel_path in content or asset_filename in content:
                matched_figure_refs.append(asset_rel_path)

        # For standalone image documents, bind its primary figure
        if not matched_figure_refs and metadata.source_category == SourceCategory.IMAGE and all_figures:
            matched_figure_refs = [f"/assets/{fig.local_image_path.name}" for fig in all_figures]

        payload: dict[str, Any] = {
            "source_category": metadata.source_category.value,
            "epistemic_weight": metadata.epistemic_weight,
            "file_path": str(metadata.file_path),
            "section_title": section_title,
        }
        return TextChunk(
            chunk_id=chunk_id,
            doc_id=metadata.doc_id,
            file_hash=metadata.file_hash,
            content=content,
            page_number=1,
            section_title=section_title,
            figure_references=matched_figure_refs,
            table_references=table_refs,
            metadata_payload=payload,
        )
