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
import re
from pathlib import Path

import networkx as nx

REPO_ROOT = Path(__file__).resolve().parents[3]
GRAPH_PATH = REPO_ROOT / "data" / "graph.gpickle"

# An entity shorter than this can't be matched usefully - it's almost always
# a stray capitalized word ("In", "It") rather than a real name.
MIN_ENTITY_LENGTH = 3

# If a non-exact entity matches more nodes than this, it's too generic to
# mean anything and is skipped entirely. Without this guard a single junk
# entity seeds a frontier of thousands of nodes, and a 2-hop walk from
# there returns most of the graph - measured at 79,617 edges / 5,615
# chunks (88% of the corpus) for one real question before this cap existed.
MAX_NODES_PER_ENTITY = 50


# The graph is read-only at query time and can be large, so it's loaded
# from disk once and reused for the life of the process (architecture.md
# 4.2: "loaded once when the backend starts") rather than re-unpickled on
# every search - the orchestrator calls search_graph up to 5 times per
# question.
_graph_cache: nx.MultiDiGraph | None = None


def load_graph(force_reload: bool = False) -> nx.MultiDiGraph:
    """Load the knowledge graph pickled by src/ingestion/build_graph.py.

    Cached after the first load. Pass force_reload=True to pick up a
    freshly rebuilt graph without restarting the process.
    """
    global _graph_cache

    if _graph_cache is not None and not force_reload:
        return _graph_cache

    if not GRAPH_PATH.exists():
        raise RuntimeError(
            f"{GRAPH_PATH} does not exist - run src/ingestion/build_graph.py first"
        )
    with open(GRAPH_PATH, "rb") as f:
        _graph_cache = pickle.load(f)
    return _graph_cache


def find_matching_nodes(graph: nx.MultiDiGraph, entity: str) -> list[str]:
    """Return nodes matching `entity`, preferring exact name matches.

    Matches on whole words, not bare substrings: "Ring" must not match
    "Cindering". An exact (case-insensitive) name match always wins and is
    returned on its own. Otherwise whole-word partial matches are returned,
    but only if there are few enough of them to be meaningful - an entity
    matching more than MAX_NODES_PER_ENTITY nodes is treated as too generic
    and matches nothing, which stops one junk entity from dragging most of
    the graph into the answer.
    """
    entity = entity.strip()
    if len(entity) < MIN_ENTITY_LENGTH:
        return []

    needle = entity.lower()
    pattern = re.compile(rf"\b{re.escape(entity)}\b", re.IGNORECASE)

    exact: list[str] = []
    partial: list[str] = []
    for node in graph.nodes:
        name = str(node)
        if name.lower() == needle:
            exact.append(node)
        elif pattern.search(name):
            partial.append(node)

    if exact:
        return exact
    if len(partial) > MAX_NODES_PER_ENTITY:
        return []
    return partial


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
