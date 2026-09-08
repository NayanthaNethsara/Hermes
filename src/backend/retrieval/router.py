from typing import Any
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.core.config import get_settings
from src.backend.core.database import get_database_session
from src.backend.ingestion.embedder import MultimodalEmbedder
from src.backend.retrieval.reranker import CrossEncoderReranker
from src.backend.retrieval.schemas import SearchQuery, SearchResponse
from src.backend.retrieval.vector_store import DocumentChunkModel, PostgresVectorStore

router = APIRouter(tags=["retrieval"])


@router.post("/retrieval/search", response_model=SearchResponse)
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


@router.get("/api/documents/{doc_id}")
@router.get("/retrieval/documents/{doc_id}")
async def get_document_details(
    doc_id: str,
    session: AsyncSession = Depends(get_database_session),
) -> dict[str, Any]:
    query = (
        select(DocumentChunkModel)
        .where(DocumentChunkModel.doc_id == doc_id)
        .order_by(DocumentChunkModel.chunk_id)
    )
    result = await session.execute(query)
    chunks = result.scalars().all()
    if not chunks:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    first_meta = chunks[0].metadata_payload or {}
    return {
        "doc_id": doc_id,
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


@router.get("/api/visuals/{filename:path}")
@router.get("/retrieval/visuals/{filename:path}")
async def get_visual_catalog_item(filename: str) -> dict[str, Any]:
    settings = get_settings()
    catalog_file = settings.extracted_assets_dir / "visual_catalog.json"
    if not catalog_file.exists():
        raise HTTPException(status_code=404, detail="Visual catalog not found")

    catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
    clean_name = filename.split("/")[-1]
    if clean_name in catalog:
        return catalog[clean_name]

    for key, value in catalog.items():
        if clean_name in key or key in clean_name:
            return value

    raise HTTPException(status_code=404, detail=f"Visual asset '{clean_name}' not found")
