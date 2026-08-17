# sinan/services/redis.py
"""Redis 客户端（懒加载单例）。Step 4 先用于取消信号，Step 5 扩展事件流/回放。"""
import redis.asyncio as aioredis
from sinan.config.settings import settings

_redis: aioredis.Redis | None = None


def create_redis() -> aioredis.Redis:
    """创建并缓存全局连接池。应用启动时调用一次，重复调用幂等。"""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=settings.redis_max_connections,
            protocol=2,  # 禁用 HELLO 握手，兼容不支持 RESP3 的 Redis/Valkey 版本
        )
    return _redis

def get_redis() -> aioredis.Redis:
    return create_redis()


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None