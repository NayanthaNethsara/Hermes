from typing import Any, TypedDict

from pydantic import BaseModel, Field

from src.backend.retrieval.schemas import SearchResultChunk


class FactRecord(BaseModel):
    fact: str
    source_id: str
    epistemic_weight: float = 1.0
    contradicts: list[str] = Field(default_factory=list)


class AgentState(TypedDict, total=False):
    root_query: str
    search_queries: list[str]
    retrieved_context: list[SearchResultChunk]
    figures: list[str]
    figure_urls: list[str]
    facts: list[FactRecord]
    iteration_count: int
    max_iterations: int
    is_sufficient: bool
    final_answer: str
    referenced_figures: list[str]
    citations: list[str]
