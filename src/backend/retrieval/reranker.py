import httpx
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
        self.endpoint = "https://api.voyageai.com/v1/rerank"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.5, min=2, max=15),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
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

        if not self.api_key:
            logger.warning("voyage_api_key_not_configured_returning_top_candidates_without_rerank")
            return candidates[:top_k]

        document_texts = [candidate.content for candidate in candidates]
        payload = {
            "model": self.model,
            "query": query,
            "documents": document_texts,
            "top_k": min(top_k * 2, len(document_texts)),
            "return_documents": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.endpoint, headers=headers, json=payload)
            if response.status_code != 200:
                logger.error(
                    "voyage_rerank_failed",
                    status_code=response.status_code,
                    body=response.text,
                )
                raise ModelInferenceError(f"Voyage rerank error: {response.text}")

            result_data = response.json()
            ranked_items = result_data.get("data", [])

        reranked_chunks: list[SearchResultChunk] = []
        for item in ranked_items:
            score = float(item.get("relevance_score", 0.0))
            if score < self.min_score:
                continue

            index = item["index"]
            candidate = candidates[index].model_copy()
            candidate.relevance_score = score
            reranked_chunks.append(candidate)

        if not reranked_chunks and ranked_items:
            highest_score = float(ranked_items[0].get("relevance_score", 0.0))
            logger.warning(
                "all_candidates_below_threshold",
                highest_score=highest_score,
                threshold=self.min_score,
            )
            raise RetrievalThresholdError(
                f"Candidate confidence {highest_score:.2f} is below required threshold {self.min_score:.2f}"
            )

        return reranked_chunks[:top_k]
