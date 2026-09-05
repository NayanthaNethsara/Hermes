"""Shared OpenRouter chat client for every agent.

All four LLM callers (Planner, Critic, Synthesizer, and the trust layer's
contradiction check) go through `chat()` here rather than each holding its
own copy of the request/retry/error-handling logic. They previously did,
which meant the same bug had to be found and fixed four times.

Two failure modes this exists to survive, both hit for real against the
free tier:

1. **A free model temporarily vanishes.** OpenRouter answers `404 "This
   model is unavailable for free"` for a model that worked seconds
   earlier and works again seconds later. Retrying the same model just
   burns the whole backoff window on a model that is out of capacity, so
   a 404 instead moves immediately to the next model in the chain.
2. **A free model is retired outright.** The model this project first
   shipped with was withdrawn from the free tier mid-build. A configured
   chain means that stops being an outage.

Set `OPENROUTER_MODEL` for the primary and `OPENROUTER_FALLBACK_MODELS`
(comma-separated) to override the chain.
"""

from __future__ import annotations

import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

# Pinned to the repo root rather than bare load_dotenv(). python-dotenv
# searches upward from the *calling file*, so a stray .env inside src/
# silently shadows the real one - which happened: a leftover
# src/backend/.env held a retired model id and an exhausted key, and every
# request from the backend used those instead of the root .env, while
# scripts run from the repo root used the correct values. Config that
# depends on which file imported it first is not config.
REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

DEFAULT_FALLBACK_MODELS = (
    "minimax/minimax-m3:free",
    "minimax/minimax-m2.7:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
)

REQUEST_TIMEOUT_SECONDS = 60


class ModelUnavailable(RuntimeError):
    """A specific model can't serve this request, but another one might.

    Raised for OpenRouter's 404 "unavailable for free" and for a model that
    returns an empty message - both mean "try the next model", not "the
    request was wrong".
    """


def require_openrouter_config() -> tuple[str, str, str]:
    """Fetch OpenRouter config or fail fast with a clear message.

    Checked up front (not inside a retried call) so a missing key fails
    immediately instead of being retried and surfacing as an opaque error.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.environ.get("OPENROUTER_MODEL")
    if not api_key or not model:
        raise RuntimeError(
            "OPENROUTER_API_KEY and OPENROUTER_MODEL must be set - copy "
            "configuration-example/.env.example to .env at the repo root "
            "and fill them in"
        )
    return api_key, base_url, model


def model_chain() -> list[str]:
    """The primary model followed by its fallbacks, de-duplicated."""
    _, _, primary = require_openrouter_config()

    configured = os.environ.get("OPENROUTER_FALLBACK_MODELS")
    fallbacks = (
        [m.strip() for m in configured.split(",") if m.strip()]
        if configured
        else list(DEFAULT_FALLBACK_MODELS)
    )

    chain = [primary]
    for model in fallbacks:
        if model not in chain:
            chain.append(model)
    return chain


def _is_retryable_api_error(exc: BaseException) -> bool:
    """True only for errors that a later identical request might survive:
    429 rate-limits, 5xx, and network/timeout failures.

    Deliberately excludes 404. OpenRouter uses 404 for "this free model is
    out of capacity", which retrying does not fix - `chat()` switches to
    another model instead, which is both faster and more likely to work.
    A 400 (genuinely invalid model id or malformed request) is never
    retried either, since it fails identically every time.
    """
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))


def _describe_http_error(exc: requests.exceptions.HTTPError) -> str:
    """Include the provider's own explanation in the error text.

    `raise_for_status()` alone produces "404 Client Error: Not Found for
    url: ..." and throws away the response body, which is the only part
    that says *why* - e.g. "Rate limit exceeded: free-models-per-day" vs
    "This model is unavailable for free". Losing that turned every failure
    into a guessing game.
    """
    response = exc.response
    if response is None:
        return str(exc)
    detail = response.text.strip()
    return f"{exc} - {detail[:400]}" if detail else str(exc)


@retry(
    retry=retry_if_exception(_is_retryable_api_error),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(6),
    reraise=True,
)
def _chat_once(model: str, system_prompt: str, user_prompt: str) -> str:
    """One model, with backoff on transient errors (~60s total).

    `reraise=True` matters: without it tenacity wraps the final failure in
    a `RetryError`, which surfaces to the user as
    `RetryError[<Future at 0x... raised HTTPError>]` and hides both the
    status code and the provider's message.
    """
    api_key, base_url, _ = require_openrouter_config()

    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code == 404:
        raise ModelUnavailable(f"{model}: {response.text.strip()[:300]}")

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        raise requests.exceptions.HTTPError(
            _describe_http_error(exc), response=response
        ) from exc

    message = (response.json().get("choices") or [{}])[0].get("message") or {}
    content = (message.get("content") or "").strip()
    if not content:
        # Reasoning models can spend their whole budget on the `reasoning`
        # field and return content=null. Downstream parsers expect text, so
        # treat this as this model failing rather than returning None.
        raise ModelUnavailable(f"{model}: returned an empty message")

    return content


def chat(system_prompt: str, user_prompt: str) -> str:
    """Send a system+user prompt to OpenRouter and return the reply text.

    Walks the model chain, moving on when a model reports itself
    unavailable or returns nothing. Raises the last error if every model
    in the chain fails.
    """
    chain = model_chain()
    last_error: Exception | None = None

    for model in chain:
        try:
            return _chat_once(model, system_prompt, user_prompt)
        except ModelUnavailable as exc:
            print(f"WARNING: {exc} - trying next model")
            last_error = exc
        except requests.exceptions.HTTPError as exc:
            # A hard HTTP failure that retries already couldn't clear (e.g.
            # an exhausted daily quota) will hit every model the same way,
            # but try the rest anyway in case it's provider-specific.
            print(f"WARNING: {model} failed: {exc} - trying next model")
            last_error = exc

    raise RuntimeError(
        f"every model failed ({', '.join(chain)}). Last error: {last_error}"
    ) from last_error
