from langgraph.graph import END, START, StateGraph

from src.backend.agents.nodes.evaluator import evaluate_sufficiency
from src.backend.agents.nodes.planner import plan_search_queries
from src.backend.agents.nodes.retriever import retrieve_evidence
from src.backend.agents.nodes.synthesizer import synthesize_answer
from src.backend.agents.nodes.visualizer import resolve_visual_assets
from src.backend.agents.state.models import AgentState


def should_continue_investigation(state: AgentState) -> str:
    if state.get("is_sufficient", False):
        return "visualizer"
    return "planner"


def build_investigator_1c_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("planner", plan_search_queries)
    workflow.add_node("retriever", retrieve_evidence)
    workflow.add_node("evaluator", evaluate_sufficiency)
    workflow.add_node("visualizer", resolve_visual_assets)
    workflow.add_node("synthesizer", synthesize_answer)

    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "retriever")
    workflow.add_edge("retriever", "evaluator")

    workflow.add_conditional_edges(
        "evaluator",
        should_continue_investigation,
        {
            "planner": "planner",
            "visualizer": "visualizer",
        },
    )

    workflow.add_edge("visualizer", "synthesizer")
    workflow.add_edge("synthesizer", END)

    return workflow.compile()
