from langgraph.graph import END, START, StateGraph

from src.backend.agents.nodes.retriever import retrieve_evidence
from src.backend.agents.nodes.synthesizer import synthesize_answer
from src.backend.agents.nodes.visualizer import resolve_visual_assets
from src.backend.agents.state.models import AgentState


def build_multimodal_1a_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("retriever", retrieve_evidence)
    workflow.add_node("visualizer", resolve_visual_assets)
    workflow.add_node("synthesizer", synthesize_answer)

    workflow.add_edge(START, "retriever")
    workflow.add_edge("retriever", "visualizer")
    workflow.add_edge("visualizer", "synthesizer")
    workflow.add_edge("synthesizer", END)

    return workflow.compile()
