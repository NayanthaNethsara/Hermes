from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SourceCategory(str, Enum):
    CODEX = "codex"
    NOVEL = "novel"
    WIKI = "wiki"
    EPHEMERA = "ephemera"
    IMAGE = "image"
    UNKNOWN = "unknown"


class EpistemicWeight(float, Enum):
    CODEX = 1.0
    WIKI = 0.8
    NOVEL = 0.6
    EPHEMERA = 0.4
    UNKNOWN = 0.5


class DocumentMetadata(BaseModel):
    doc_id: str
    file_hash: str
    file_path: Path
    source_category: SourceCategory = SourceCategory.UNKNOWN
    epistemic_weight: float = EpistemicWeight.UNKNOWN.value
    page_count: int = 1


class ExtractedFigure(BaseModel):
    figure_id: str
    page_number: int
    bounding_box: tuple[float, float, float, float]
    local_image_path: Path
    caption: str = ""


class ExtractedTable(BaseModel):
    table_id: str
    page_number: int
    bounding_box: tuple[float, float, float, float]
    local_image_path: Path | None = None
    markdown_content: str = ""


class TextChunk(BaseModel):
    chunk_id: str
    doc_id: str
    file_hash: str
    content: str
    page_number: int
    section_title: str = ""
    figure_references: list[str] = Field(default_factory=list)
    table_references: list[str] = Field(default_factory=list)
    metadata_payload: dict[str, Any] = Field(default_factory=dict)
