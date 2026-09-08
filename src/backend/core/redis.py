import json
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio import Redis

from src.backend.core.config import get_settings
from src.backend.core.logging import get_logger

logger = get_logger("redis")

_redis_client: Redis | None = None


async def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
        )
    return _redis_client


async def close_redis_client() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("redis_connection_closed")


async def check_redis_health() -> bool:
    try:
        client = await get_redis_client()
        return bool(await client.ping())
    except Exception as error:
        logger.warning("redis_healthcheck_failed", error=str(error))
        return False


async def redis_get_json(key: str) -> Any | None:
    try:
        client = await get_redis_client()
        raw_data = await client.get(key)
        if raw_data is None:
            return None
        return json.loads(raw_data)
    except Exception as error:
        logger.warning("redis_get_failed", key=key, error=str(error))
        return None


async def redis_set_json(key: str, value: Any, ttl_seconds: int = 3600) -> None:
    try:
        client = await get_redis_client()
        serialized = json.dumps(value)
        await client.set(key, serialized, ex=ttl_seconds)
    except Exception as error:
        logger.warning("redis_set_failed", key=key, error=str(error))


async def redis_delete(key: str) -> None:
    try:
        client = await get_redis_client()
        await client.delete(key)
    except Exception as error:
        logger.warning("redis_delete_failed", key=key, error=str(error))


async def redis_delete_pattern(pattern: str) -> None:
    try:
        client = await get_redis_client()
        keys = await client.keys(pattern)
        if keys:
            await client.delete(*keys)
    except Exception as error:
        logger.warning("redis_delete_pattern_failed", pattern=pattern, error=str(error))
