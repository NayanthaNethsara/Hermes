import os
from typing import Any

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from src.backend.core.config import get_settings
from src.backend.core.logging import get_logger

logger = get_logger(__name__)

LLM_TIMEOUT_SECONDS = 45.0

_model_cache: dict[float, BaseChatModel] = {}


class OpenRouterChatModel(BaseChatModel):
    model_name: str
    api_key: str
    base_url: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.1
    timeout: float = 60.0

    @property
    def _llm_type(self) -> str:
        return "openrouter"

    def _format_messages(self, messages: list[BaseMessage]) -> list[dict[str, str]]:
        formatted = []
        for message in messages:
            role = "user"
            if message.type == "system":
                role = "system"
            elif message.type in ["ai", "assistant"]:
                role = "assistant"
            content = message.content if isinstance(message.content, str) else str(message.content)
            formatted.append({"role": role, "content": content})
        return formatted

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload = {
            "model": self.model_name,
            "messages": self._format_messages(messages),
            "temperature": self.temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            text_out = data["choices"][0]["message"]["content"]
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text_out))])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload = {
            "model": self.model_name,
            "messages": self._format_messages(messages),
            "temperature": self.temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            text_out = data["choices"][0]["message"]["content"]
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text_out))])


class DummyChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "dummy"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content='{"answer": "Configuration required: Set GCP_PROJECT_ID or GEMINI_API_KEY.", "referenced_figures": []}'
                    )
                )
            ]
        )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)


def get_chat_model(temperature: float = 0.1) -> BaseChatModel:
    if temperature in _model_cache:
        return _model_cache[temperature]

    model = _build_chat_model(temperature)
    _model_cache[temperature] = model
    return model


def _build_chat_model(temperature: float) -> BaseChatModel:
    settings = get_settings()

    google_api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if settings.gcp_project_id or google_api_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            kwargs: dict[str, Any] = {
                "model": settings.gemini_model,
                "temperature": temperature,
                "timeout": LLM_TIMEOUT_SECONDS,
            }

            if google_api_key:
                kwargs["google_api_key"] = google_api_key

            if settings.gcp_project_id:
                kwargs["project"] = settings.gcp_project_id

            if settings.gcp_location:
                kwargs["location"] = settings.gcp_location

            logger.info(
                "initializing_google_genai_chat_model",
                model=settings.gemini_model,
                project=settings.gcp_project_id,
            )
            return ChatGoogleGenerativeAI(**kwargs)
        except Exception as error:
            logger.warning(
                "google_genai_initialization_failed_falling_back",
                error_detail=str(error),
            )

    if settings.openrouter_api_key:
        return OpenRouterChatModel(
            model_name=settings.openrouter_model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            temperature=temperature,
        )

    logger.warning("no_chat_model_provider_configured_using_dummy")
    return DummyChatModel()
