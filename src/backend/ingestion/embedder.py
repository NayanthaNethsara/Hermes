from pathlib import Path
from typing import Any

import voyageai
from PIL import Image
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.backend.core.config import get_settings
from src.backend.core.exceptions import ModelInferenceError
from src.backend.core.logging import get_logger

logger = get_logger(__name__)


class MultimodalEmbedder:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.voyage_api_key
        self.model = model or settings.voyage_embedding_model
        self.client = voyageai.Client(api_key=self.api_key) if self.api_key else None

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def embed_texts(
        self, texts: list[str], input_type: str = "document", batch_size: int = 20
    ) -> list[list[float]]:
        if not texts:
            return []

        if not self.client:
            logger.warning("voyage_api_key_not_configured_returning_mock_vectors")
            return [[0.0] * 1024 for _ in texts]

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            inputs = [[text] for text in batch]
            try:
                result = self.client.multimodal_embed(
                    inputs=inputs,
                    model=self.model,
                    input_type=input_type,
                )
                all_embeddings.extend(result.embeddings)
            except Exception as error:
                logger.error("voyage_embed_batch_failed", error_detail=str(error))
                raise ModelInferenceError(f"Voyage embedding failed: {error}")

        return all_embeddings

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def embed_interleaved(
        self, text: str, image_paths: list[Path], input_type: str = "document"
    ) -> list[float]:
        if not self.client:
            logger.warning("voyage_api_key_not_configured_returning_mock_vector")
            return [0.0] * 1024

        content_items: list[Any] = [text]
        for path in image_paths:
            if path.exists():
                try:
                    img = Image.open(path)
                    content_items.append(img)
                except Exception as img_err:
                    logger.warning("failed_opening_image_for_embedding", path=str(path), error=str(img_err))

        try:
            result = self.client.multimodal_embed(
                inputs=[content_items],
                model=self.model,
                input_type=input_type,
            )
            return result.embeddings[0]
        except Exception as error:
            logger.error("voyage_interleaved_embed_failed", error_detail=str(error))
            raise ModelInferenceError(f"Voyage interleaved embedding failed: {error}")
