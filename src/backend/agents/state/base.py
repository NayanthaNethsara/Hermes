from src.backend.agents.state.models import AgentState
from src.backend.core.config import get_settings


def create_initial_state(query: str, max_iterations: int | None = None) -> AgentState:
    settings = get_settings()
    return AgentState(
        root_query=query,
        search_queries=[query],
        retrieved_context=[],
        figures=[],
        figure_urls=[],
        facts=[],
        iteration_count=0,
        max_iterations=max_iterations or settings.max_search_iterations,
        is_sufficient=False,
        final_answer="",
        referenced_figures=[],
        citations=[],
    )
