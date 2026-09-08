from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.core.database import get_database_session
from src.backend.ingestion.embedder import MultimodalEmbedder
from src.backend.retrieval.reranker import CrossEncoderReranker
from src.backend.retrieval.schemas import SearchQuery, SearchResponse
from src.backend.retrieval.vector_store import DocumentChunkModel, PostgresVectorStore
from src.backend.retrieval.visuals import lookup_visual

router = APIRouter(tags=["retrieval"])


@router.post("/retrieval/search", response_model=SearchResponse, summary="Hybrid search without the agent graph")
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


@router.get("/api/documents/{doc_id}", summary="Get a document with all of its chunks")
@router.get("/retrieval/documents/{doc_id}")
async def get_document_details(
    doc_id: str,
    session: AsyncSession = Depends(get_database_session),
) -> dict[str, Any]:
    clean_doc_id = doc_id.split("|")[0].strip()
    query = (
        select(DocumentChunkModel)
        .where(DocumentChunkModel.doc_id == clean_doc_id)
        .order_by(DocumentChunkModel.chunk_id)
    )
    result = await session.execute(query)
    chunks = result.scalars().all()
    if not chunks:
        raise HTTPException(status_code=404, detail=f"Document '{clean_doc_id}' not found")

    first_meta = chunks[0].metadata_payload or {}
    return {
        "doc_id": clean_doc_id,
        "source_category": first_meta.get("source_category", "unknown"),
        "epistemic_weight": first_meta.get("epistemic_weight", 0.5),
        "total_chunks": len(chunks),
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "section_title": (c.metadata_payload or {}).get("section_title", "General"),
                "content": c.content,
                "figures": (c.metadata_payload or {}).get("figure_references", []),
                "tables": (c.metadata_payload or {}).get("table_references", []),
            }
            for c in chunks
        ],
    }


@router.get("/api/visuals/{filename:path}", summary="Get catalog metadata for a visual asset")
@router.get("/retrieval/visuals/{filename:path}")
async def get_visual_catalog_item(filename: str) -> dict[str, Any]:
    details = lookup_visual(filename)
    if details is None:
        clean_name = filename.split("/")[-1]
        raise HTTPException(status_code=404, detail=f"Visual asset '{clean_name}' not found")
    return details
