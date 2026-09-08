import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    delete,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.core.database import Base, get_database_session
from src.backend.core.exceptions import DatabaseUnavailableError, is_connectivity_error
from src.backend.core.logging import get_logger
from src.backend.retrieval.schemas import SearchResultChunk

logger = get_logger(__name__)


class DocumentFileModel(Base):
    __tablename__ = "documents"

    file_hash = Column(String(64), primary_key=True)
    doc_id = Column(String(128), nullable=False, index=True)
    file_path = Column(Text, nullable=False)
    source_category = Column(String(32), nullable=False)
    epistemic_weight = Column(Float, nullable=False, default=1.0)
    chunk_count = Column(Integer, default=0)
    figure_count = Column(Integer, default=0)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())


class DocumentChunkModel(Base):
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id = Column(String(128), unique=True, nullable=False, index=True)
    doc_id = Column(String(128), nullable=False, index=True)
    file_hash = Column(String(64), ForeignKey("documents.file_hash", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1024), nullable=False)
    tsv = Column(TSVECTOR)
    metadata_payload = Column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_document_chunks_tsv", "tsv", postgresql_using="gin"),
    )


class PostgresVectorStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def has_document(self, file_hash: str) -> bool:
        query = select(func.count()).select_from(DocumentFileModel).where(DocumentFileModel.file_hash == file_hash)
        result = await self.session.execute(query)
        count = result.scalar_one_or_none() or 0
        return count > 0

    async def delete_document(self, file_hash: str) -> None:
        stmt = delete(DocumentFileModel).where(DocumentFileModel.file_hash == file_hash)
        await self.session.execute(stmt)
        await self.session.flush()

    async def record_document(
        self,
        doc_id: str,
        file_hash: str,
        file_path: str,
        source_category: str,
        epistemic_weight: float,
        chunk_count: int,
        figure_count: int,
    ) -> None:
        record = DocumentFileModel(
            file_hash=file_hash,
            doc_id=doc_id,
            file_path=file_path,
            source_category=source_category,
            epistemic_weight=epistemic_weight,
            chunk_count=chunk_count,
            figure_count=figure_count,
        )
        await self.session.merge(record)
        await self.session.flush()

    async def insert_chunks(
        self,
        chunks: list[dict[str, Any]],
    ) -> None:
        for item in chunks:
            chunk_obj = DocumentChunkModel(
                chunk_id=item["chunk_id"],
                doc_id=item["doc_id"],
                file_hash=item["file_hash"],
                content=item["content"],
                embedding=item["embedding"],
                tsv=func.to_tsvector("english", item["content"]),
                metadata_payload=item.get("metadata_payload", {}),
            )
            self.session.add(chunk_obj)
        await self.session.flush()

    async def hybrid_search_rrf(
        self,
        query_text: str,
        query_vector: list[float],
        top_k: int = 50,
        rrf_k: int = 60,
    ) -> list[SearchResultChunk]:
        vector_str = "[" + ",".join(str(x) for x in query_vector) + "]"

        hybrid_query = text("""
            WITH vector_matches AS (
                SELECT 
                    chunk_id,
                    doc_id,
                    content,
                    metadata_payload,
                    ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:vector_param AS vector)) as vector_rank,
                    (1 - (embedding <=> CAST(:vector_param AS vector))) as vector_score
                FROM document_chunks
                ORDER BY embedding <=> CAST(:vector_param AS vector)
                LIMIT :candidate_limit
            ),
            keyword_matches AS (
                SELECT 
                    chunk_id,
                    doc_id,
                    content,
                    metadata_payload,
                    ROW_NUMBER() OVER (ORDER BY ts_rank(tsv, plainto_tsquery('english', :query_param)) DESC) as keyword_rank,
                    ts_rank(tsv, plainto_tsquery('english', :query_param)) as keyword_score
                FROM document_chunks
                WHERE tsv @@ plainto_tsquery('english', :query_param)
                ORDER BY keyword_score DESC
                LIMIT :candidate_limit
            )
            SELECT 
                COALESCE(v.chunk_id, k.chunk_id) as chunk_id,
                COALESCE(v.doc_id, k.doc_id) as doc_id,
                COALESCE(v.content, k.content) as content,
                COALESCE(v.metadata_payload, k.metadata_payload) as metadata_payload,
                v.vector_score,
                k.keyword_score,
                (COALESCE(1.0 / (:rrf_k + v.vector_rank), 0.0) + COALESCE(1.0 / (:rrf_k + k.keyword_rank), 0.0)) as rrf_score
            FROM vector_matches v
            FULL OUTER JOIN keyword_matches k ON v.chunk_id = k.chunk_id
            ORDER BY rrf_score DESC
            LIMIT :final_top_k;
        """)

        try:
            result = await self.session.execute(
                hybrid_query,
                {
                    "vector_param": vector_str,
                    "query_param": query_text,
                    "candidate_limit": top_k,
                    "rrf_k": rrf_k,
                    "final_top_k": top_k,
                },
            )
            rows = result.fetchall()

            search_results: list[SearchResultChunk] = []
            for row in rows:
                meta = row.metadata_payload or {}
                fig_refs = meta.get("figure_references", [])
                tbl_refs = meta.get("table_references", [])
                search_results.append(
                    SearchResultChunk(
                        chunk_id=row.chunk_id,
                        doc_id=row.doc_id,
                        content=row.content,
                        relevance_score=float(row.rrf_score),
                        vector_score=float(row.vector_score) if row.vector_score is not None else None,
                        keyword_score=float(row.keyword_score) if row.keyword_score is not None else None,
                        figure_references=fig_refs,
                        table_references=tbl_refs,
                        metadata_payload=meta,
                    )
                )
            return search_results

        except Exception as error:
            if is_connectivity_error(error):
                # An outage must not read as "the archive holds no evidence".
                logger.warning(
                    "sql_rrf_hybrid_search_database_unavailable",
                    error_detail=str(error),
                )
                raise DatabaseUnavailableError() from error

            logger.warning(
                "sql_rrf_hybrid_search_failed_returning_empty",
                error_detail=str(error),
            )
            return []
