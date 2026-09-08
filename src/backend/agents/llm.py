import os
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from src.backend.core.config import get_settings
from src.backend.core.logging import get_logger

logger = get_logger(__name__)


def get_chat_model(temperature: float = 0.1) -> BaseChatModel:
    settings = get_settings()

    google_api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if settings.gcp_project_id or google_api_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            kwargs: dict[str, Any] = {
                "model": settings.gemini_model,
                "temperature": temperature,
                "automatic_function_calling_config": {"disable": True},
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
        from langchain_core.messages import AIMessage, BaseMessage
        from tenacity import retry, stop_after_attempt, wait_exponential

        class OpenRouterChatModel(BaseChatModel):
            model_name: str = settings.openrouter_model
            api_key: str = settings.openrouter_api_key
            base_url: str = settings.openrouter_base_url
            temp: float = temperature

            @property
            def _llm_type(self) -> str:
                return "openrouter"

            def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> Any:
                import requests
                from langchain_core.outputs import ChatGeneration, ChatResult

                formatted = [{"role": "user", "content": m.content} for m in messages]
                payload = {
                    "model": self.model_name,
                    "messages": formatted,
                    "temperature": self.temp,
                }
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                resp = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=60)
                resp.raise_for_status()
                text_out = resp.json()["choices"][0]["message"]["content"]
                generation = ChatGeneration(message=AIMessage(content=text_out))
                return ChatResult(generations=[generation])

        return OpenRouterChatModel()

    from langchain_core.messages import AIMessage, BaseMessage

    class DummyChatModel(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "dummy"

        def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> Any:
            from langchain_core.outputs import ChatGeneration, ChatResult

            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content='{"answer": "Configuration required: Set GCP_PROJECT_ID or GEMINI_API_KEY.", "referenced_figures": []}'
                        )
                    )
                ]
            )

    logger.warning("no_chat_model_provider_configured_using_dummy")
    return DummyChatModel()
