import voyageai
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.backend.core.config import get_settings
from src.backend.core.exceptions import ModelInferenceError, RetrievalThresholdError
from src.backend.core.logging import get_logger
from src.backend.retrieval.schemas import SearchResultChunk

logger = get_logger(__name__)


class CrossEncoderReranker:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        min_score: float | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.voyage_api_key
        self.model = model or settings.voyage_rerank_model
        self.min_score = min_score if min_score is not None else settings.rerank_score_threshold
        self.client = voyageai.Client(api_key=self.api_key) if self.api_key else None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.5, min=2, max=15),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def rerank(
        self,
        query: str,
        candidates: list[SearchResultChunk],
        top_k: int = 5,
    ) -> list[SearchResultChunk]:
        if not candidates:
            return []

        if not self.client:
            logger.warning("voyage_api_key_not_configured_returning_top_candidates_without_rerank")
            return candidates[:top_k]

        document_texts = [candidate.content for candidate in candidates]

        try:
            result = self.client.rerank(
                query=query,
                documents=document_texts,
                model=self.model,
                top_k=min(top_k * 2, len(document_texts)),
            )
            ranked_items = result.results
        except Exception as error:
            logger.error("voyage_rerank_failed", error_detail=str(error))
            raise ModelInferenceError(f"Voyage rerank error: {error}")

        reranked_chunks: list[SearchResultChunk] = []
        for item in ranked_items:
            score = float(item.relevance_score)
            if score < self.min_score:
                continue

            candidate = candidates[item.index].model_copy()
            candidate.relevance_score = score
            reranked_chunks.append(candidate)

        if not reranked_chunks and ranked_items:
            highest_score = float(ranked_items[0].relevance_score)
            logger.warning(
                "all_candidates_below_threshold",
                highest_score=highest_score,
                threshold=self.min_score,
            )
            raise RetrievalThresholdError(
                f"Candidate confidence {highest_score:.2f} is below required threshold {self.min_score:.2f}"
            )

        return reranked_chunks[:top_k]
