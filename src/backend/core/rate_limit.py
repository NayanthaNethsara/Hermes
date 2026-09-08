import time
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.backend.core.config import get_settings
from src.backend.core.logging import get_logger
from src.backend.core.redis import get_redis_client

logger = get_logger("rate_limit")

RATE_LIMITED_PATHS = {
    "/api/ask",
    "/api/ask/stream",
    "/retrieval/search",
    "/api/retrieval/search",
}


def get_client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "anonymous_client"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if not any(path.startswith(prefix) for prefix in RATE_LIMITED_PATHS):
            return await call_next(request)

        settings = get_settings()
        limit = settings.redis_rate_limit_requests
        window_seconds = settings.redis_rate_limit_window_seconds

        client_ip = get_client_identifier(request)
        now_epoch = int(time.time())
        window_index = now_epoch // window_seconds
        cache_key = f"ratelimit:{client_ip}:{window_index}"
        time_to_reset = window_seconds - (now_epoch % window_seconds)

        remaining_requests = limit
        try:
            redis = await get_redis_client()
            current_count = await redis.incr(cache_key)
            if current_count == 1:
                await redis.expire(cache_key, window_seconds + 2)

            remaining_requests = max(0, limit - current_count)

            if current_count > limit:
                logger.warning(
                    "rate_limit_exceeded",
                    client_ip=client_ip,
                    path=path,
                    current_count=current_count,
                    limit=limit,
                )
                headers = {
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(time_to_reset),
                    "Retry-After": str(time_to_reset),
                }
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please wait before submitting more queries."},
                    headers=headers,
                )
        except Exception as error:
            logger.warning("rate_limit_check_bypassed", error=str(error))

        response: Response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining_requests)
        response.headers["X-RateLimit-Reset"] = str(time_to_reset)
        return response
