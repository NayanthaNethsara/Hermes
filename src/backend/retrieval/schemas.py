from typing import Any

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    query: str
    top_k: int = 50
    rerank_top_k: int = 5
    filter_category: str | None = None
    min_score: float = 0.50


class SearchResultChunk(BaseModel):
    chunk_id: str
    doc_id: str
    content: str
    relevance_score: float = 0.0
    vector_score: float | None = None
    keyword_score: float | None = None
    figure_references: list[str] = Field(default_factory=list)
    table_references: list[str] = Field(default_factory=list)
    metadata_payload: dict[str, Any] = Field(default_factory=dict)


class RankedResult(BaseModel):
    chunks: list[SearchResultChunk]
    total_candidates: int = 0
    query_latency_ms: float = 0.0


class SearchResponse(BaseModel):
    results: list[SearchResultChunk]
    referenced_figures: list[str] = Field(default_factory=list)
