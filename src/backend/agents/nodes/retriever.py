from typing import Any

from src.backend.agents.state.models import AgentState
from src.backend.core.database import session_scope
from src.backend.ingestion.embedder import MultimodalEmbedder
from src.backend.retrieval.reranker import CrossEncoderReranker
from src.backend.retrieval.schemas import SearchResultChunk
from src.backend.retrieval.vector_store import PostgresVectorStore


async def retrieve_evidence(state: AgentState) -> dict[str, Any]:
    search_queries = state.get("search_queries", [])
    if not search_queries:
        search_queries = [state.get("root_query", "")]

    embedder = MultimodalEmbedder()
    reranker = CrossEncoderReranker()
    existing_chunks = state.get("retrieved_context", [])
    existing_ids = {c.chunk_id for c in existing_chunks}
    new_chunks: list[SearchResultChunk] = []
    collected_figures: list[str] = list(state.get("figures", []))

    async with session_scope() as session:
        store = PostgresVectorStore(session)

        for query in search_queries:
            query_vectors = await embedder.embed_texts([query], input_type="query")
            query_vector = query_vectors[0] if query_vectors else [0.0] * 1024

            candidates = await store.hybrid_search_rrf(
                query_text=query,
                query_vector=query_vector,
                top_k=50,
            )

            try:
                top_results = await reranker.rerank(
                    query=query,
                    candidates=candidates,
                    top_k=5,
                )
            except Exception:
                top_results = candidates[:5]

            for chunk in top_results:
                if chunk.chunk_id not in existing_ids:
                    existing_ids.add(chunk.chunk_id)
                    new_chunks.append(chunk)
                    collected_figures.extend(chunk.figure_references)

    all_chunks = existing_chunks + new_chunks
    iteration = state.get("iteration_count", 0) + 1
    unique_figures = list(dict.fromkeys(collected_figures))

    return {
        "retrieved_context": all_chunks,
        "figures": unique_figures,
        "iteration_count": iteration,
    }
