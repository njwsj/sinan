# sinan/services/generation_event_bus.py
"""可持久化的生成事件总线。

对齐参考项目 page/services/generation_event_bus.py：
- Redis List 存事件：sinan:generation:events:{session_id}
- Redis INCR 发序列号：sinan:generation:events:seq:{session_id}
- event_id = 序列号的十进制字符串，客户端 Last-Event-ID / cursor 直接可比大小
- 终止事件（completed/error/cancelled/chat/awaiting_confirmation）后给 key 打 TTL，
  保证"任务结束后再连接仍能收到 completed"，同时不无限占用内存
- subscribe 用轮询而非 pub/sub：多实例、断线重连、回放三件事只依赖一份有序数据

Redis 不可用时（settings.event_bus_backend = "memory"）退化为进程内实现，
接口一致，但不跨实例、不跨重启，只用于本地开发。

两个 key 的分工：
  sinan:generation:events:{session_id}      → Redis List，存事件完整内容
  sinan:generation:events:seq:{session_id}  → Redis String，存当前最新序列号（纯整数）
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol

from sinan.config.settings import settings
from sinan.models.events import GenerationEvent
from sinan.services.redis import get_redis

logger = logging.getLogger(__name__)

# Redis key 前缀
_KEY_PREFIX = "sinan:generation:events"
# seq key 只存一个整数，让 get_last_event_id 能直接读到最新序列号，
# 不用 LRANGE 读整个 List 再解析最后一条，减少一次 IO。
_SEQ_KEY_PREFIX = "sinan:generation:events:seq"


def event_key(session_id: str) -> str:
    """返回存储该 session 事件列表的 Redis List key。"""
    return f"{_KEY_PREFIX}:{session_id}"


def seq_key(session_id: str) -> str:
    """返回存储该 session 当前序列号的 Redis String key。"""
    return f"{_SEQ_KEY_PREFIX}:{session_id}"


def parse_cursor(cursor: Any) -> int:
    """把 Last-Event-ID / cursor 解析成整数序号，非法值一律当 0（从头回放）。"""
    if cursor in (None, "", "0", "0-0"):
        return 0
    if isinstance(cursor, bytes):
        cursor = cursor.decode("utf-8", errors="ignore")
    try:
        return max(int(str(cursor).strip()), 0)
    except (TypeError, ValueError):
        return 0


def format_cursor(seq: int) -> str:
    """把整数序列号格式化为字符串游标，保证非负。"""
    try:
        return str(max(int(seq), 0))
    except (TypeError, ValueError):
        return "0"


class EventBus(Protocol):
    """两个后端共享的接口协议（类似其他语言的 interface）。

    路由和 runner 只依赖这个协议，不感知底层是 Redis 还是内存。
    RedisEventBus 和 InMemoryEventBus 无需继承此类，只需实现相同的方法签名即可。
    """

    async def publish(self, session_id: str, event_type: str, data: dict,
                      *, job_id: str | None = None,
                      marker: str | None = None) -> str:
        """发布一条事件，返回该事件的 event_id（序列号字符串）。"""
        ...

    async def replay(self, session_id: str,
                     cursor: str | None = None) -> list[GenerationEvent]:
        """一次性回放 cursor 之后的全部历史事件，用于断线重连时补历史。"""
        ...

    def subscribe(self, session_id: str,
                  cursor: str | None = None) -> AsyncIterator[GenerationEvent]:
        """持续订阅新事件，从 cursor 之后开始，遇终止事件由调用方退出。"""
        ...

    async def get_last_event_id(self, session_id: str) -> str:
        """返回当前最新事件的 event_id，供 session_init 填 resume_cursor 用。"""
        ...

    async def close(self, session_id: str) -> None:
        """任务结束后主动给 key 打 TTL，幂等操作。"""
        ...

    async def trim(self, session_id: str) -> None:
        """手动裁剪超长事件列表，保持在 sse_max_events 以内。"""
        ...


class RedisEventBus:
    """Redis List 实现，可跨实例、可跨重启回放。生产环境使用。"""

    def __init__(self) -> None:
        self._max_len = settings.sse_max_events          # 每个 session 最多保留的事件条数
        self._terminal_ttl = settings.sse_terminal_ttl_seconds  # 终止事件后 key 的存活秒数
        self._poll_seconds = settings.sse_poll_seconds   # subscribe 轮询间隔

    async def publish(self, session_id: str, event_type: str, data: dict,
                      *, job_id: str | None = None,
                      marker: str | None = None) -> str:
        """发布一条事件到 Redis List。

        步骤：
          1. INCR seq_key → 拿到唯一递增序列号（原子操作，多实例安全）
          2. 构造 GenerationEvent 对象
          3. RPUSH event.to_record() → 追加到 List 尾部
          4. LTRIM → 保持 List 长度不超过 _max_len
          5. 若是终止事件 → 给两个 key 都打 TTL（晚到客户端仍能拿到 completed）
        """
        redis = get_redis()
        seq = int(await redis.incr(seq_key(session_id)))   # 原子自增，多实例安全
        event = GenerationEvent(
            event_id=format_cursor(seq),
            event=event_type,
            session_id=session_id,
            job_id=job_id,
            marker=marker,
            data=data or {},
        )
        key = event_key(session_id)
        await redis.rpush(key, event.to_record())
        await redis.ltrim(key, -self._max_len, -1)          # 保留最新的 _max_len 条
        if event.is_terminal:
            # 终止事件后保留一段时间：晚到的客户端仍能拿到 completed
            await redis.expire(key, self._terminal_ttl)
            await redis.expire(seq_key(session_id), self._terminal_ttl)
        return event.event_id

    async def replay(self, session_id: str,
                     cursor: str | None = None) -> list[GenerationEvent]:
        """一次性读出 cursor 之后的全部历史事件。

        用于断线重连：客户端带着上次收到的 Last-Event-ID 过来，
        这里过滤掉已收到的，把剩余事件一次性返回，不丢、不重复。
        """
        current = parse_cursor(cursor)
        rows = await get_redis().lrange(event_key(session_id), 0, -1)  # 读全部
        events: list[GenerationEvent] = []
        for raw in rows or []:
            event = GenerationEvent.from_record(raw)
            if event is None:
                continue  # 跳过损坏记录
            if parse_cursor(event.event_id) > current:
                events.append(event)
        return events

    async def subscribe(self, session_id: str,
                        cursor: str | None = None) -> AsyncIterator[GenerationEvent]:
        """持续轮询新事件，每隔 _poll_seconds 秒 LRANGE 一次。

        用轮询而非 Redis pub/sub 的原因：
          - 轮询天然支持断线重连（游标可恢复）
          - 多实例部署时每个实例都能独立订阅同一个 List
          - 不需要额外维护 pub/sub channel 的生命周期

        终止事件由调用方（路由）判断 event.is_terminal 后退出循环。
        假设 Redis List 里现在有 3 条事件，客户端上次收到了第 2 条，断线重连时带来 cursor="2"。

        初始状态

        current = 2   # 从 cursor 解析出来，意思是"seq ≤ 2 的我都收过了"

        Redis List 内容：
          seq=1  step(analyze)
          seq=2  step(code)
          seq=3  completed       ← 断线期间新产生的

        第一次循环
        rows = await redis.lrange(key, 0, -1)
        # rows = [seq1的原始字符串, seq2的原始字符串, seq3的原始字符串]

        遍历每条：

        seq=1，1 > 2 为 False，跳过
        seq=2，2 > 2 为 False，跳过
        seq=3，3 > 2 为 True
        current = 3（推进游标）
        yield event（把 completed 发给调用方）
        调用方收到 completed，判断 event.is_terminal 为 True，退出 async for，循环结束。
        """
        current = parse_cursor(cursor)
        key = event_key(session_id)
        redis = get_redis()
        while True:
            rows = await redis.lrange(key, 0, -1)
            for raw in rows or []:
                event = GenerationEvent.from_record(raw)
                if event is None:
                    continue
                seq = parse_cursor(event.event_id)
                if seq > current:
                    current = seq   # 推进游标，下次轮询跳过已 yield 的事件
                    yield event
            await asyncio.sleep(self._poll_seconds)

    async def get_last_event_id(self, session_id: str) -> str:
        """直接读 seq key 获取最新序列号，避免 LRANGE 读整个 List。"""
        current = await get_redis().get(seq_key(session_id))
        return format_cursor(parse_cursor(current))

    async def close(self, session_id: str) -> None:
        """任务结束后主动打 TTL，幂等，供 runner finalize 调用。"""
        redis = get_redis()
        await redis.expire(event_key(session_id), self._terminal_ttl)
        await redis.expire(seq_key(session_id), self._terminal_ttl)

    async def trim(self, session_id: str) -> None:
        """手动裁剪事件列表，保持在 _max_len 以内。"""
        await get_redis().ltrim(event_key(session_id), -self._max_len, -1)


class InMemoryEventBus:
    """开发环境 fallback：进程内列表，接口与 RedisEventBus 完全一致。

    与旧版 asyncio.Queue 的关键区别：
      事件存在列表里不消耗，多个订阅者各自持有自己的 current 游标，互不干扰。
      旧版 Queue.get() 是消费型的，两个客户端会互相抢事件。

    局限：不跨实例、不跨重启，仅用于本地开发调试。
    """

    def __init__(self) -> None:
        self._events: dict[str, list[GenerationEvent]] = {}  # session_id → 事件列表
        self._seq: dict[str, int] = {}                        # session_id → 当前序列号
        self._poll_seconds = settings.sse_poll_seconds
        self._max_len = settings.sse_max_events

    async def publish(self, session_id: str, event_type: str, data: dict,
                      *, job_id: str | None = None,
                      marker: str | None = None) -> str:
        seq = self._seq.get(session_id, 0) + 1
        self._seq[session_id] = seq
        event = GenerationEvent(
            event_id=format_cursor(seq), event=event_type, session_id=session_id,
            job_id=job_id, marker=marker, data=data or {},
        )
        bucket = self._events.setdefault(session_id, [])
        bucket.append(event)
        if len(bucket) > self._max_len:
            del bucket[: len(bucket) - self._max_len]  # 超长时从头裁剪
        return event.event_id

    async def replay(self, session_id: str,
                     cursor: str | None = None) -> list[GenerationEvent]:
        current = parse_cursor(cursor)
        return [e for e in self._events.get(session_id, [])
                if parse_cursor(e.event_id) > current]

    async def subscribe(self, session_id: str,
                        cursor: str | None = None) -> AsyncIterator[GenerationEvent]:
        current = parse_cursor(cursor)
        while True:
            for event in list(self._events.get(session_id, [])):
                seq = parse_cursor(event.event_id)
                if seq > current:
                    current = seq
                    yield event
            await asyncio.sleep(self._poll_seconds)

    async def get_last_event_id(self, session_id: str) -> str:
        return format_cursor(self._seq.get(session_id, 0))

    async def close(self, session_id: str) -> None:
        return None  # 内存实现不做过期，进程退出即释放

    async def trim(self, session_id: str) -> None:
        bucket = self._events.get(session_id)
        if bucket and len(bucket) > self._max_len:
            del bucket[: len(bucket) - self._max_len]


def _build_bus() -> EventBus:
    """根据配置决定使用哪个后端，模块加载时执行一次。

    EVENT_BUS_BACKEND=memory  → InMemoryEventBus（本地开发）
    默认                      → RedisEventBus（生产）
    """
    if settings.event_bus_backend == "memory":
        logger.warning("event bus backend = memory：事件不跨实例、不跨重启")
        return InMemoryEventBus()
    return RedisEventBus()


# 模块级单例：调用方 `from sinan.services.generation_event_bus import event_bus` 即可，
# 不感知底层是 Redis 还是内存，切换只需改环境变量。
event_bus: EventBus = _build_bus()