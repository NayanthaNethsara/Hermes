from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.core.database import get_database_session
from src.backend.ingestion.embedder import MultimodalEmbedder
from src.backend.retrieval.reranker import CrossEncoderReranker
from src.backend.retrieval.schemas import SearchQuery, SearchResponse
from src.backend.retrieval.vector_store import PostgresVectorStore

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


@router.post("/search", response_model=SearchResponse)
async def search_documents(
    query_payload: SearchQuery,
    session: AsyncSession = Depends(get_database_session),
) -> SearchResponse:
    embedder = MultimodalEmbedder()
    query_vectors = await embedder.embed_texts([query_payload.query], input_type="query")
    query_vector = query_vectors[0] if query_vectors else [0.0] * 1024

    store = PostgresVectorStore(session)
    candidates = await store.hybrid_search_rrf(
        query_text=query_payload.query,
        query_vector=query_vector,
        top_k=query_payload.top_k,
    )

    reranker = CrossEncoderReranker(min_score=query_payload.min_score)
    top_chunks = await reranker.rerank(
        query=query_payload.query,
        candidates=candidates,
        top_k=query_payload.rerank_top_k,
    )

    referenced_figures: list[str] = []
    for chunk in top_chunks:
        referenced_figures.extend(chunk.figure_references)

    unique_figures = list(dict.fromkeys(referenced_figures))
    return SearchResponse(results=top_chunks, referenced_figures=unique_figures)
