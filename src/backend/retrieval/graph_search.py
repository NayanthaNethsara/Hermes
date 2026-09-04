"""Graph search over the knowledge graph (NetworkX).

Exports search_graph(entities, max_hops), which starts from any node
whose name partially matches one of the given entities and walks up to
max_hops outgoing edges, returning every relationship found along the way.

Pure graph traversal - no LLM calls, no API cost. Run
src/ingestion/build_graph.py first; this module only reads what it wrote
to data/graph.gpickle.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import networkx as nx

REPO_ROOT = Path(__file__).resolve().parents[3]
GRAPH_PATH = REPO_ROOT / "data" / "graph.gpickle"


def load_graph() -> nx.MultiDiGraph:
    """Load the knowledge graph pickled by src/ingestion/build_graph.py."""
    if not GRAPH_PATH.exists():
        raise RuntimeError(
            f"{GRAPH_PATH} does not exist - run src/ingestion/build_graph.py first"
        )
    with open(GRAPH_PATH, "rb") as f:
        return pickle.load(f)


def find_matching_nodes(graph: nx.MultiDiGraph, entity: str) -> list[str]:
    """Return every node whose name contains `entity` (case-insensitive)."""
    needle = entity.lower()
    return [node for node in graph.nodes if needle in str(node).lower()]


def search_graph(entities: list[str], max_hops: int = 2) -> list[dict]:
    """Walk up to max_hops outgoing edges from nodes matching `entities`.

    `entities` are matched against node names with a case-insensitive
    partial match. Returns one dict per relationship found, each shaped:
    {from, relation, to, source_chunk_id, trust_tier}. Edges already
    visited are not returned twice, even if reached by multiple paths.
    """
    graph = load_graph()

    frontier: set[str] = set()
    for entity in entities:
        frontier.update(find_matching_nodes(graph, entity))

    visited_nodes: set[str] = set(frontier)
    seen_edges: set[tuple] = set()
    results: list[dict] = []

    for _ in range(max_hops):
        next_frontier: set[str] = set()

        for node in frontier:
            if node not in graph:
                continue
            for source, target, key, data in graph.out_edges(node, keys=True, data=True):
                edge_id = (source, target, key)
                if edge_id in seen_edges:
                    continue
                seen_edges.add(edge_id)

                results.append(
                    {
                        "from": source,
                        "relation": data.get("relation"),
                        "to": target,
                        "source_chunk_id": data.get("source_chunk_id"),
                        "trust_tier": data.get("trust_tier"),
                    }
                )

                if target not in visited_nodes:
                    next_frontier.add(target)

        visited_nodes.update(next_frontier)
        frontier = next_frontier
        if not frontier:
            break

    return results


if __name__ == "__main__":
    import sys

    entity_args = sys.argv[1:] or ["test entity"]
    for edge in search_graph(entity_args):
        print(edge)
