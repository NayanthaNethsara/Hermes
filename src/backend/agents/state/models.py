from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from src.backend.retrieval.schemas import SearchResultChunk


class FactRecord(BaseModel):
    fact: str
    source_id: str
    epistemic_weight: float = 1.0
    contradicts: list[str] = Field(default_factory=list)


class ConversationalInvestigatorState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    root_query: str
    search_query: str
    session_id: str
    session_summary: str
    is_conversational: bool
    planned_queries: list[str]

    active_chunks: list[SearchResultChunk]
    active_figures: list[str]

    verified_chunks: list[SearchResultChunk]
    contradictions: list[dict[str, Any]]

    final_answer: str
    referenced_figures: list[str]
    citations: list[str]
    reasoning_steps: list[dict[str, Any]]

    # Compatibility aliases
    retrieved_context: list[SearchResultChunk]
    figures: list[str]
    figure_urls: list[str]
    facts: list[FactRecord]
    iteration_count: int
    max_iterations: int
    is_sufficient: bool


AgentState = ConversationalInvestigatorState
