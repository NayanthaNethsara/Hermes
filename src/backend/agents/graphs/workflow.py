from typing import Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from src.backend.agents.nodes.arbitrator import arbitrate_evidence
from src.backend.agents.nodes.guardrail import guardrail_input
from src.backend.agents.nodes.planner import plan_search_queries
from src.backend.agents.nodes.retriever import retrieve_evidence
from src.backend.agents.nodes.synthesizer import synthesize_answer
from src.backend.agents.state.models import ConversationalInvestigatorState
from src.backend.core.database import get_connection_pool
from src.backend.core.logging import get_logger

logger = get_logger("workflow")

_cached_graph = None
_cached_checkpointer = None


def build_unified_graph(checkpointer=None):
    workflow = StateGraph(ConversationalInvestigatorState)

    workflow.add_node("guardrail", guardrail_input)
    workflow.add_node("planner", plan_search_queries)
    workflow.add_node("retriever", retrieve_evidence)
    workflow.add_node("arbitrator", arbitrate_evidence)
    workflow.add_node("synthesizer", synthesize_answer)

    def route_after_guardrail(state: ConversationalInvestigatorState) -> str:
        if state.get("is_conversational"):
            return "synthesizer"
        return "planner"

    workflow.add_edge(START, "guardrail")
    workflow.add_conditional_edges("guardrail", route_after_guardrail, ["planner", "synthesizer"])
    workflow.add_edge("planner", "retriever")
    workflow.add_edge("retriever", "arbitrator")
    workflow.add_edge("arbitrator", "synthesizer")
    workflow.add_edge("synthesizer", END)

    return workflow.compile(checkpointer=checkpointer)


async def get_checkpointer():
    global _cached_checkpointer
    if _cached_checkpointer is not None:
        return _cached_checkpointer

    try:
        pool = await get_connection_pool()
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        _cached_checkpointer = checkpointer
        logger.info("postgres_checkpointer_initialized_successfully")
        return _cached_checkpointer
    except Exception as error:
        logger.warning("postgres_checkpointer_failed_using_memory_saver", error=str(error))
        _cached_checkpointer = MemorySaver()
        return _cached_checkpointer


async def get_compiled_graph():
    global _cached_graph
    if _cached_graph is not None:
        return _cached_graph

    checkpointer = await get_checkpointer()
    _cached_graph = build_unified_graph(checkpointer=checkpointer)
    return _cached_graph
