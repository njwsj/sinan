# sinan/services/redis.py
"""Redis 客户端（懒加载单例）。Step 4 先用于取消信号，Step 5 扩展事件流/回放。"""
import redis.asyncio as aioredis
from sinan.config.settings import settings

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None