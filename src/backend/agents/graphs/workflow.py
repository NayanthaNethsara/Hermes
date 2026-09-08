import asyncio
import time

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from src.backend.agents.nodes.arbitrator import arbitrate_evidence
from src.backend.agents.nodes.critic import assess_sufficiency
from src.backend.agents.nodes.guardrail import guardrail_input
from src.backend.agents.nodes.planner import plan_search_queries
from src.backend.agents.nodes.retriever import retrieve_evidence
from src.backend.agents.nodes.synthesizer import synthesize_answer
from src.backend.agents.state.models import SEARCH_AGAIN, ConversationalInvestigatorState
from src.backend.core.config import get_settings
from src.backend.core.database import get_connection_pool
from src.backend.core.exceptions import summarize_error
from src.backend.core.logging import get_logger

logger = get_logger("workflow")

_cached_graph = None
_cached_graph_checkpointer = None
_cached_checkpointer = None
_checkpointer_is_fallback = False
_checkpointer_retry_after = 0.0
_checkpointer_lock = asyncio.Lock()

# While degraded, retry Postgres at most this often instead of on every request.
CHECKPOINTER_RETRY_COOLDOWN_SECONDS = 15.0


def build_unified_graph(checkpointer=None):
    workflow = StateGraph(ConversationalInvestigatorState)

    workflow.add_node("guardrail", guardrail_input)
    workflow.add_node("planner", plan_search_queries)
    workflow.add_node("retriever", retrieve_evidence)
    workflow.add_node("critic", assess_sufficiency)
    workflow.add_node("arbitrator", arbitrate_evidence)
    workflow.add_node("synthesizer", synthesize_answer)

    def route_after_guardrail(state: ConversationalInvestigatorState) -> str:
        if state.get("is_conversational"):
            return "synthesizer"
        return "planner"

    def route_after_critic(state: ConversationalInvestigatorState) -> str:
        if state.get("evidence_verdict") != SEARCH_AGAIN:
            return "arbitrator"
        max_hops = state.get("max_iterations") or get_settings().max_search_iterations
        if state.get("iteration_count", 0) >= max_hops:
            return "arbitrator"
        if not state.get("planned_queries"):
            return "arbitrator"
        return "retriever"

    workflow.add_edge(START, "guardrail")
    workflow.add_conditional_edges("guardrail", route_after_guardrail, ["planner", "synthesizer"])
    workflow.add_edge("planner", "retriever")
    workflow.add_edge("retriever", "critic")
    workflow.add_conditional_edges("critic", route_after_critic, ["retriever", "arbitrator"])
    workflow.add_edge("arbitrator", "synthesizer")
    workflow.add_edge("synthesizer", END)

    return workflow.compile(checkpointer=checkpointer)


async def get_checkpointer():
    """Postgres-backed checkpointer, degrading to in-memory when it is down.

    The in-memory saver is never cached as final: every later call retries
    Postgres, so the graph upgrades itself once the database is reachable again.
    """
    global _cached_checkpointer, _checkpointer_is_fallback, _checkpointer_retry_after

    if _cached_checkpointer is not None and not _checkpointer_is_fallback:
        return _cached_checkpointer

    async with _checkpointer_lock:
        if _cached_checkpointer is not None and not _checkpointer_is_fallback:
            return _cached_checkpointer
        if _cached_checkpointer is not None and time.monotonic() < _checkpointer_retry_after:
            return _cached_checkpointer

        try:
            pool = await get_connection_pool()
            checkpointer = AsyncPostgresSaver(pool)
            await checkpointer.setup()
            _cached_checkpointer = checkpointer
            _checkpointer_is_fallback = False
            logger.info("postgres_checkpointer_initialized_successfully")
        except Exception as error:
            logger.warning(
                "postgres_checkpointer_failed_using_memory_saver",
                error=summarize_error(error),
            )
            if _cached_checkpointer is None or not _checkpointer_is_fallback:
                _cached_checkpointer = MemorySaver()
            _checkpointer_is_fallback = True
            _checkpointer_retry_after = time.monotonic() + CHECKPOINTER_RETRY_COOLDOWN_SECONDS

        return _cached_checkpointer


async def get_compiled_graph():
    global _cached_graph, _cached_graph_checkpointer

    checkpointer = await get_checkpointer()
    if _cached_graph is None or _cached_graph_checkpointer is not checkpointer:
        _cached_graph = build_unified_graph(checkpointer=checkpointer)
        _cached_graph_checkpointer = checkpointer
    return _cached_graph
