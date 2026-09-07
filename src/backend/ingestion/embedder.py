import base64
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.backend.core.config import get_settings
from src.backend.core.exceptions import ModelInferenceError
from src.backend.core.logging import get_logger

logger = get_logger(__name__)


def encode_image_to_base64(image_path: Path) -> str:
    with open(image_path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("utf-8")
    suffix = image_path.suffix.lstrip(".").lower()
    mime_type = "jpeg" if suffix in ["jpg", "jpeg"] else suffix
    return f"data:image/{mime_type};base64,{encoded}"


class MultimodalEmbedder:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.voyage_api_key
        self.model = model or settings.voyage_embedding_model
        self.endpoint = "https://api.voyageai.com/v1/multimodalembeddings"

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def embed_texts(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        if not texts:
            return []

        inputs = [[{"type": "text", "text": text}] for text in texts]
        return await self._call_voyage_api(inputs=inputs, input_type=input_type)

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def embed_interleaved(
        self, text: str, image_paths: list[Path], input_type: str = "document"
    ) -> list[float]:
        content_items: list[dict[str, str]] = [{"type": "text", "text": text}]
        for path in image_paths:
            if path.exists():
                base64_uri = encode_image_to_base64(path)
                content_items.append({"type": "image_base64", "image_base64": base64_uri})

        embeddings = await self._call_voyage_api(inputs=[content_items], input_type=input_type)
        return embeddings[0]

    async def _call_voyage_api(
        self, inputs: list[list[dict[str, str]]], input_type: str
    ) -> list[list[float]]:
        if not self.api_key:
            logger.warning("voyage_api_key_not_configured_returning_mock_vectors")
            return [[0.0] * 1024 for _ in inputs]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "inputs": inputs,
            "input_type": input_type,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(self.endpoint, headers=headers, json=payload)
            if response.status_code != 200:
                logger.error(
                    "voyage_embedding_failed",
                    status_code=response.status_code,
                    body=response.text,
                )
                raise ModelInferenceError(f"Voyage API error {response.status_code}: {response.text}")

            data = response.json()
            return [item["embedding"] for item in data["data"]]
