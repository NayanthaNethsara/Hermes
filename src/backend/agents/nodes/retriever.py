import hashlib
from typing import Any

from src.backend.agents.state.models import AgentState
from src.backend.core.config import get_settings
from src.backend.core.database import session_scope
from src.backend.core.logging import get_logger
from src.backend.core.redis import redis_get_json, redis_set_json
from src.backend.ingestion.embedder import MultimodalEmbedder
from src.backend.retrieval.reranker import CrossEncoderReranker
from src.backend.retrieval.schemas import SearchResultChunk
from src.backend.retrieval.vector_store import PostgresVectorStore

logger = get_logger("retriever")


async def retrieve_evidence(state: AgentState) -> dict[str, Any]:
    steps = list(state.get("reasoning_steps", []))

    search_query = state.get("search_query") or state.get("root_query", "")
    planned_queries = state.get("planned_queries") or state.get("search_queries", [])
    queries_to_run = planned_queries if planned_queries else ([search_query] if search_query else [])

    if not queries_to_run:
        steps.append({
            "step": len(steps) + 1,
            "action": "Hybrid Archive Retrieval",
            "found": "No queries planned — 0 chunks retrieved",
        })
        return {
            "active_chunks": [],
            "active_figures": [],
            "retrieved_context": [],
            "figures": [],
            "figure_urls": [],
            "reasoning_steps": steps,
        }

    settings = get_settings()
    embedder = MultimodalEmbedder()
    reranker = CrossEncoderReranker()
    existing_chunks = state.get("retrieved_context", [])
    existing_ids = {c.chunk_id for c in existing_chunks}
    new_chunks: list[SearchResultChunk] = []
    collected_figures: list[str] = list(state.get("figures", []))

    async with session_scope() as session:
        store = PostgresVectorStore(session)

        for query in queries_to_run:
            normalized_query = query.strip().lower()
            query_hash = hashlib.sha256(normalized_query.encode("utf-8")).hexdigest()
            cache_key = f"cache:retrieval:{query_hash}"

            cached_payload = await redis_get_json(cache_key)
            if cached_payload is not None and isinstance(cached_payload, dict):
                cached_chunk_dicts = cached_payload.get("chunks", [])
                cached_chunks = [
                    SearchResultChunk.model_validate(item) for item in cached_chunk_dicts
                ]
                top_results = cached_chunks
                logger.info(
                    "retrieval_cache_hit",
                    query=query,
                    chunks_count=len(top_results),
                )
            else:
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

                await redis_set_json(
                    cache_key,
                    {
                        "chunks": [chunk.model_dump() for chunk in top_results],
                        "figures": [
                            fig for chunk in top_results for fig in chunk.figure_references
                        ],
                    },
                    ttl_seconds=settings.redis_cache_ttl_seconds,
                )
                logger.info(
                    "retrieval_cache_miss_persisted",
                    query=query,
                    chunks_count=len(top_results),
                )

            for chunk in top_results:
                if chunk.chunk_id not in existing_ids:
                    existing_ids.add(chunk.chunk_id)
                    new_chunks.append(chunk)
                    collected_figures.extend(chunk.figure_references)
                    meta = chunk.metadata_payload or {}
                    logger.info(
                        "retrieved_chunk_embedding_match",
                        doc_id=chunk.doc_id,
                        category=meta.get("source_category", "unknown"),
                        authority=meta.get("epistemic_weight", 0.5),
                        cosine_similarity=round(chunk.vector_score, 4) if chunk.vector_score is not None else None,
                        fulltext_score=round(chunk.keyword_score, 4) if chunk.keyword_score is not None else None,
                        rrf_score=round(chunk.relevance_score, 4),
                    )

    all_chunks = existing_chunks + new_chunks
    iteration = state.get("iteration_count", 0) + 1
    unique_figures = list(dict.fromkeys(collected_figures))
    searched_queries = list(dict.fromkeys(list(state.get("searched_queries", [])) + queries_to_run))

    top_doc_names = list(dict.fromkeys([c.doc_id for c in new_chunks]))[:4]
    docs_summary = ", ".join(f"`{d}`" for d in top_doc_names) if top_doc_names else "none"
    hop_label = f"Hop {iteration}: " if iteration > 1 else ""
    retrieval_detail = (
        f"{hop_label}searched {len(queries_to_run)} query(s), "
        f"added {len(new_chunks)} new passage(s) from [{docs_summary}], "
        f"{len(all_chunks)} total in evidence"
    )
    if unique_figures:
        retrieval_detail += f", {len(unique_figures)} visual figure(s) linked"

    steps.append({
        "step": len(steps) + 1,
        "action": "Hybrid Archive Retrieval",
        "found": retrieval_detail,
    })

    return {
        "active_chunks": all_chunks,
        "active_figures": unique_figures,
        "retrieved_context": all_chunks,
        "figures": unique_figures,
        "figure_urls": unique_figures,
        "iteration_count": iteration,
        "last_hop_yield": len(new_chunks),
        "searched_queries": searched_queries,
        "reasoning_steps": steps,
    }
